import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.api.deps import get_current_user, get_db, get_redis
from app.core.config import settings
from app.core.logging import get_logger
from app.middleware.rate_limit import enforce_rate_limit
from app.models.conversation import MessageRole
from app.models.user import User
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.repository_repository import RepositoryRepository
from app.rag.chain import run_rag_stream
from app.rag.summarizer import maybe_summarize
from app.schemas.chat import AskRequest, ConversationOut
from app.services.cache_service import CacheService

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = await ConversationRepository(db).get_owned(conversation_id, current_user.id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


@router.post("/chat/ask", dependencies=[Depends(enforce_rate_limit)])
async def ask(
    payload: AskRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """
    Server-Sent Events streaming endpoint for all AI features (ask_codebase,
    explain_file, generate_docs, architecture_analyzer, bug_investigation,
    related_files). Each SSE frame is a small JSON envelope so the frontend
    can distinguish token chunks from the final "done" event carrying
    source references.

    Flow: rate limit -> auth -> ownership check -> cache lookup ->
    retrieve + stream from LLM -> persist assistant message -> cache write.
    """
    repo_dal = RepositoryRepository(db)
    repository = await repo_dal.get_owned(payload.repository_id, current_user.id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    conv_dal = ConversationRepository(db)
    if payload.conversation_id:
        conversation = await conv_dal.get_owned(payload.conversation_id, current_user.id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    else:
        conversation = await conv_dal.create(
            repository_id=payload.repository_id,
            user_id=current_user.id,
            title=payload.question[:80],
        )
        await db.commit()

    await conv_dal.add_message(
        conversation_id=conversation.id, role=MessageRole.USER, content=payload.question
    )
    await db.commit()

    cache = CacheService(redis_client)

    # Only cache the default Q&A mode; the other modes are less repetitive
    # and cheap to skip caching for.
    if payload.mode == "ask_codebase":
        cached = await cache.get(str(payload.repository_id), repository.commit_sha, payload.question)
        if cached:
            async def _cached_stream():
                yield f"data: {json.dumps({'type': 'token', 'content': cached['answer']})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'source_references': cached['source_references'], 'cached': True})}\n\n"

            await conv_dal.add_message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=cached["answer"],
                source_references=cached["source_references"],
            )
            await db.commit()
            return StreamingResponse(_cached_stream(), media_type="text/event-stream")

    history_rows = await conv_dal.recent_messages(conversation.id, settings.MAX_HISTORY_MESSAGES)
    total_count = await conv_dal.count_messages(conversation.id)

    token_stream, rag_result = await run_rag_stream(
        mode=payload.mode,
        question=payload.question,
        repository_id=str(payload.repository_id),
        summary=conversation.summary,
        history_rows=history_rows[:-1],  # exclude the message we just added
        file_path=payload.file_path,
    )

    async def event_generator():
        full_answer_parts: list[str] = []
        try:
            async for token in token_stream:
                full_answer_parts.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.error("stream_error", error=str(exc), conversation_id=str(conversation.id))
            yield f"data: {json.dumps({'type': 'error', 'message': 'Generation failed. Please retry.'})}\n\n"
            return

        full_answer = "".join(full_answer_parts)

        # Persist after streaming completes, even if the client disconnected
        # mid-stream -- we still want the answer saved for history/cache.
        await conv_dal.add_message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=full_answer,
            source_references=rag_result.source_references,
        )

        if payload.mode == "ask_codebase" and rag_result.context_used:
            await cache.set(
                str(payload.repository_id),
                repository.commit_sha,
                payload.question,
                {"answer": full_answer, "source_references": rag_result.source_references},
            )

        summary = await maybe_summarize(
            conversation_id=str(conversation.id),
            total_message_count=total_count,
            older_messages=history_rows[: -settings.MAX_HISTORY_MESSAGES] if total_count > settings.MAX_HISTORY_MESSAGES else [],
            existing_summary=conversation.summary,
        )
        if summary:
            await conv_dal.update_summary(conversation.id, summary)

        await db.commit()

        yield f"data: {json.dumps({'type': 'done', 'source_references': rag_result.source_references, 'conversation_id': str(conversation.id)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
