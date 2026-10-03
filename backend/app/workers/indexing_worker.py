"""
Kafka consumer entrypoint, run as its own container/process
(`python -m app.workers.indexing_worker`).

Responsibilities:
- Consume `repository.index.requested` events.
- Idempotency: skip if the referenced IndexingJob is already COMPLETED.
- Run the indexing pipeline (clone -> chunk -> embed -> upsert).
- Update Postgres status.
- Invalidate the Redis AI-response cache for the repository.
- Publish `repository.index.completed` or `repository.index.failed`.
- Retry transient failures with backoff; DLQ-style: after max retries,
  publish a failure event and stop, so a poison message doesn't spin forever.

Uses a *sync* SQLAlchemy session deliberately -- worker processes benefit
from simple, sequential, one-message-at-a-time semantics rather than an
asyncio event loop fighting confluent-kafka's sync C client.
"""
import json
import signal
import sys
import time

import redis
from confluent_kafka import Consumer, KafkaError, KafkaException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.models.indexing_job import IndexingJob
from app.models.repository import IndexStatus, Repository
from app.services.indexing_service import index_repository
from app.workers.kafka_producer import publish_event

configure_logging()
logger = get_logger("indexing_worker")

_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=_engine)

_redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

_running = True


class TransientIndexingError(Exception):
    """Errors worth retrying: network blips, rate limits, etc."""


def _invalidate_cache(repository_id: str) -> None:
    cursor = 0
    while True:
        cursor, keys = _redis_client.scan(cursor=cursor, match=f"ai_cache:{repository_id}:*", count=200)
        if keys:
            _redis_client.delete(*keys)
        if cursor == 0:
            break


@retry(
    retry=retry_if_exception_type(TransientIndexingError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def _run_pipeline_with_retry(*, repository_id, project_id, github_url, branch):
    try:
        return index_repository(
            repository_id=repository_id, project_id=project_id, github_url=github_url, branch=branch
        )
    except (ConnectionError, TimeoutError) as exc:
        raise TransientIndexingError(str(exc)) from exc


def handle_index_requested(db: Session, payload: dict) -> None:
    job_id = payload["job_id"]
    repository_id = payload["repository_id"]

    job = db.get(IndexingJob, job_id)
    repo = db.get(Repository, repository_id)
    if job is None or repo is None:
        logger.warning("job_or_repo_missing", job_id=job_id, repository_id=repository_id)
        return

    # --- Idempotency guard ---
    # At-least-once Kafka delivery means this handler can run more than
    # once for the same job_id. If it already completed, skip re-work.
    if job.status == IndexStatus.COMPLETED:
        logger.info("job_already_completed_skip", job_id=job_id)
        return

    job.status = IndexStatus.INDEXING
    repo.index_status = IndexStatus.INDEXING
    db.commit()

    try:
        result = _run_pipeline_with_retry(
            repository_id=repository_id,
            project_id=payload["project_id"],
            github_url=payload["github_url"],
            branch=payload.get("branch", "main"),
        )
    except Exception as exc:  # noqa: BLE001 - worker boundary: log, persist, publish, move on
        logger.error("indexing_failed", job_id=job_id, repository_id=repository_id, error=str(exc))
        job.status = IndexStatus.FAILED
        job.error_message = str(exc)[:2000]
        repo.index_status = IndexStatus.FAILED
        db.commit()
        publish_event(
            settings.TOPIC_INDEX_FAILED,
            key=repository_id,
            payload={"job_id": job_id, "repository_id": repository_id, "error": str(exc)[:500]},
        )
        return

    job.status = IndexStatus.COMPLETED
    job.chunks_indexed = result.chunk_count
    job.duration_ms = result.duration_ms
    repo.index_status = IndexStatus.COMPLETED
    repo.commit_sha = result.commit_sha
    repo.primary_language = result.primary_language
    repo.chunk_count = result.chunk_count
    repo.last_indexed_at = str(int(time.time()))
    db.commit()

    _invalidate_cache(repository_id)

    publish_event(
        settings.TOPIC_INDEX_COMPLETED,
        key=repository_id,
        payload={
            "job_id": job_id,
            "repository_id": repository_id,
            "chunk_count": result.chunk_count,
            "commit_sha": result.commit_sha,
        },
    )
    logger.info("indexing_completed", job_id=job_id, repository_id=repository_id, chunks=result.chunk_count)


def _shutdown(signum, frame):  # noqa: ARG001
    global _running
    logger.info("worker_shutdown_signal_received")
    _running = False


def main() -> None:
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    consumer = Consumer(
        {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": settings.KAFKA_CONSUMER_GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,  # manual commit AFTER successful processing = at-least-once, no data loss
        }
    )
    consumer.subscribe([settings.TOPIC_INDEX_REQUESTED])
    logger.info("worker_started", topic=settings.TOPIC_INDEX_REQUESTED)

    try:
        while _running:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                if msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                    logger.warning("topic_not_yet_available", topic=settings.TOPIC_INDEX_REQUESTED)
                    continue
                if not msg.error().fatal():
                    logger.warning("kafka_consumer_error", error=str(msg.error()))
                    continue
                raise KafkaException(msg.error())

            try:
                payload = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.error("malformed_message_skipped", error=str(exc))
                consumer.commit(msg)
                continue

            with SyncSessionLocal() as db:
                handle_index_requested(db, payload)

            consumer.commit(msg)
    finally:
        consumer.close()
        logger.info("worker_stopped")


if __name__ == "__main__":
    main()
    sys.exit(0)
