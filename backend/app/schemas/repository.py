from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.repository import IndexStatus


class RepositoryCreate(BaseModel):
    github_url: str = Field(description="e.g. https://github.com/org/repo")
    branch: str = "main"


class RepositoryOut(BaseModel):
    id: UUID
    project_id: UUID
    github_url: str
    branch: str
    commit_sha: str | None
    primary_language: str | None
    index_status: IndexStatus
    chunk_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class IndexTriggerResponse(BaseModel):
    """Returned immediately; API never blocks on indexing."""

    job_id: UUID
    repository_id: UUID
    status: IndexStatus
