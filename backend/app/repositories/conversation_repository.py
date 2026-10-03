from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, Message, MessageRole


class ConversationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, repository_id: UUID, user_id: UUID, title: str | None = None) -> Conversation:
        conv = Conversation(repository_id=repository_id, user_id=user_id, title=title)
        self.db.add(conv)
        await self.db.flush()
        return conv

    async def get_owned(self, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        result = await self.db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def count_messages(self, conversation_id: UUID) -> int:
        result = await self.db.execute(
            select(Message).where(Message.conversation_id == conversation_id)
        )
        return len(result.scalars().all())

    async def add_message(
        self,
        *,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        source_references: list[str] | None = None,
        token_usage: dict | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            source_references=source_references,
            token_usage=token_usage,
        )
        self.db.add(message)
        await self.db.flush()
        return message

    async def update_summary(self, conversation_id: UUID, summary: str) -> None:
        conv = await self.db.get(Conversation, conversation_id)
        if conv:
            conv.summary = summary
            await self.db.flush()
