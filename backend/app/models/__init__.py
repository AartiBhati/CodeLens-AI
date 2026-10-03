"""Import every model so Alembic autogenerate and Base.metadata see them all."""
from app.models.user import User  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.repository import Repository, IndexStatus  # noqa: F401
from app.models.indexing_job import IndexingJob  # noqa: F401
from app.models.conversation import Conversation, Message, MessageRole  # noqa: F401
