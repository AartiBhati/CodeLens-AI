import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IndexStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class Repository(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "repositories"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    github_url: Mapped[str] = mapped_column(String(512), nullable=False)
    github_repo_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    primary_language: Mapped[str | None] = mapped_column(String(64), nullable=True)

    index_status: Mapped[IndexStatus] = mapped_column(
        Enum(IndexStatus,
            name="index_status_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            )
            , default=IndexStatus.PENDING, nullable=False, index=True
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_indexed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="repositories")  # noqa: F821
    indexing_jobs: Mapped[list["IndexingJob"]] = relationship(  # noqa: F821
        back_populates="repository", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(  # noqa: F821
        back_populates="repository", cascade="all, delete-orphan"
    )
