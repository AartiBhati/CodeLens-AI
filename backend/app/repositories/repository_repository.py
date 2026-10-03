from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.indexing_job import IndexingJob
from app.models.project import Project
from app.models.repository import IndexStatus, Repository


class RepositoryRepository:
    """Data access for `Repository` rows. Named verbosely to avoid clashing
    with the architectural 'repository pattern' concept vs. a git repository."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, project_id: UUID, github_url: str, branch: str) -> Repository:
        repo = Repository(project_id=project_id, github_url=github_url, branch=branch)
        self.db.add(repo)
        await self.db.flush()
        return repo

    async def get_owned(self, repo_id: UUID, owner_id: UUID) -> Repository | None:
        """A single query that enforces: repo -> project -> owner == current user."""
        result = await self.db.execute(
            select(Repository)
            .join(Project, Project.id == Repository.project_id)
            .where(Repository.id == repo_id, Project.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: UUID) -> list[Repository]:
        result = await self.db.execute(select(Repository).where(Repository.project_id == project_id))
        return list(result.scalars().all())

    async def update_status(
        self, repo_id: UUID, status: IndexStatus, **fields
    ) -> None:
        repo = await self.db.get(Repository, repo_id)
        if repo is None:
            return
        repo.index_status = status
        for key, value in fields.items():
            setattr(repo, key, value)
        await self.db.flush()

    async def create_job(self, repo_id: UUID, requested_commit_sha: str | None = None) -> IndexingJob:
        job = IndexingJob(repository_id=repo_id, requested_commit_sha=requested_commit_sha)
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_job(self, job_id: UUID) -> IndexingJob | None:
        return await self.db.get(IndexingJob, job_id)

    async def update_job(self, job_id: UUID, **fields) -> None:
        job = await self.db.get(IndexingJob, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        await self.db.flush()
