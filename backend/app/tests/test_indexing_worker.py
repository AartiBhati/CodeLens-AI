from unittest.mock import MagicMock, patch

from app.models.indexing_job import IndexingJob
from app.models.repository import IndexStatus, Repository
from app.workers.indexing_worker import handle_index_requested


def _make_payload(job_id="job-1", repo_id="repo-1"):
    return {
        "job_id": job_id,
        "repository_id": repo_id,
        "project_id": "project-1",
        "github_url": "https://github.com/octocat/Hello-World",
        "branch": "main",
    }


def test_skips_already_completed_job_idempotently():
    """Simulates a redelivered Kafka message (at-least-once semantics):
    the worker must not re-run indexing for a job that already succeeded."""
    db = MagicMock()
    job = IndexingJob(id="job-1", repository_id="repo-1", status=IndexStatus.COMPLETED)
    repo = Repository(id="repo-1", project_id="project-1", github_url="https://github.com/x/y")
    db.get.side_effect = lambda model, _id: job if model is IndexingJob else repo

    with patch("app.workers.indexing_worker._run_pipeline_with_retry") as mock_pipeline:
        handle_index_requested(db, _make_payload())
        mock_pipeline.assert_not_called()


def test_successful_indexing_updates_status_and_publishes_completed_event():
    db = MagicMock()
    job = IndexingJob(id="job-1", repository_id="repo-1", status=IndexStatus.QUEUED)
    repo = Repository(id="repo-1", project_id="project-1", github_url="https://github.com/x/y")
    db.get.side_effect = lambda model, _id: job if model is IndexingJob else repo

    fake_result = MagicMock(commit_sha="sha123", primary_language="Python", chunk_count=42, duration_ms=1000)

    with patch("app.workers.indexing_worker._run_pipeline_with_retry", return_value=fake_result), \
         patch("app.workers.indexing_worker.publish_event") as mock_publish, \
         patch("app.workers.indexing_worker._invalidate_cache") as mock_invalidate:
        handle_index_requested(db, _make_payload())

    assert job.status == IndexStatus.COMPLETED
    assert job.chunks_indexed == 42
    assert repo.index_status == IndexStatus.COMPLETED
    assert repo.commit_sha == "sha123"
    mock_invalidate.assert_called_once_with("repo-1")
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[0] == "repository.index.completed"


def test_failed_indexing_marks_job_and_repo_failed_and_publishes_failure_event():
    db = MagicMock()
    job = IndexingJob(id="job-1", repository_id="repo-1", status=IndexStatus.QUEUED)
    repo = Repository(id="repo-1", project_id="project-1", github_url="https://github.com/x/y")
    db.get.side_effect = lambda model, _id: job if model is IndexingJob else repo

    with patch(
        "app.workers.indexing_worker._run_pipeline_with_retry", side_effect=RuntimeError("clone failed")
    ), patch("app.workers.indexing_worker.publish_event") as mock_publish:
        handle_index_requested(db, _make_payload())

    assert job.status == IndexStatus.FAILED
    assert "clone failed" in job.error_message
    assert repo.index_status == IndexStatus.FAILED
    assert mock_publish.call_args.args[0] == "repository.index.failed"


def test_missing_job_or_repo_is_a_noop():
    db = MagicMock()
    db.get.return_value = None
    with patch("app.workers.indexing_worker._run_pipeline_with_retry") as mock_pipeline:
        handle_index_requested(db, _make_payload())
        mock_pipeline.assert_not_called()
