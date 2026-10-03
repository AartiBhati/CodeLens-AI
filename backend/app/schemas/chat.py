from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.conversation import MessageRole


class AskRequest(BaseModel):
    repository_id: UUID
    conversation_id: UUID | None = None
    question: str = Field(min_length=1, max_length=4000)
    mode: str = Field(
        default="ask_codebase",
        description="ask_codebase | explain_file | generate_docs | architecture_analyzer | bug_investigation | related_files",
    )
    file_path: str | None = None


class MessageOut(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    source_references: list[str] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: UUID
    repository_id: UUID
    title: str | None
    created_at: datetime
    messages: list[MessageOut] = []

    model_config = {"from_attributes": True}
