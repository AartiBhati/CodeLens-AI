from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


class ProjectRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, owner_id: UUID, name: str, description: str | None) -> Project:
        project = Project(owner_id=owner_id, name=name, description=description)
        self.db.add(project)
        await self.db.flush()
        return project

    async def list_for_owner(self, owner_id: UUID) -> list[Project]:
        result = await self.db.execute(select(Project).where(Project.owner_id == owner_id))
        return list(result.scalars().all())

    async def get_owned(self, project_id: UUID, owner_id: UUID) -> Project | None:
        """Enforces repository isolation: a project is only visible to its owner."""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
        )
        return result.scalar_one_or_none()
