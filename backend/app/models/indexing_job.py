import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.repository import IndexStatus
from sqlalchemy import Enum


class IndexingJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    One row per indexing attempt. The `id` doubles as the Kafka event's
    idempotency key: the worker checks this table before doing any work so a
    redelivered message (at-least-once Kafka semantics) never double-indexes.
    """

    __tablename__ = "indexing_jobs"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[IndexStatus] = mapped_column(
        Enum(IndexStatus, 
             name="index_status_enum",
             values_callable=lambda enum_cls: [member.value for member in enum_cls],
             ), default=IndexStatus.QUEUED, nullable=False
    )
    requested_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunks_indexed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    repository: Mapped["Repository"] = relationship(back_populates="indexing_jobs")  # noqa: F821
