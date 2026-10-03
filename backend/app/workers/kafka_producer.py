import json
from functools import lru_cache

from confluent_kafka import Producer

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def get_producer() -> Producer:
    return Producer({"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS})


def _delivery_callback(err, msg):
    if err is not None:
        logger.error("kafka_delivery_failed", error=str(err), topic=msg.topic())
    else:
        logger.info("kafka_delivered", topic=msg.topic(), partition=msg.partition())


def publish_event(topic: str, key: str, payload: dict) -> None:
    """Fire-and-forget publish. `poll(0)` drains the delivery-report queue
    without blocking the API request; a background flush happens on
    process shutdown (see main.py lifespan)."""
    producer = get_producer()
    producer.produce(
        topic=topic,
        key=key.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
        callback=_delivery_callback,
    )
    producer.poll(0)


def flush_producer(timeout: float = 5.0) -> None:
    get_producer().flush(timeout)
