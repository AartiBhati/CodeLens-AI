"""
When a conversation grows past HISTORY_SUMMARY_TRIGGER messages, we
collapse the older turns into a rolling summary stored on the Conversation
row, and only keep the most recent MAX_HISTORY_MESSAGES in full. This keeps
prompt size (and cost/latency) bounded while preserving long-range context.
"""
from app.core.config import settings
from app.rag.llm import get_chat_model
from app.rag.prompts import SUMMARIZE_HISTORY_PROMPT


async def maybe_summarize(
    *, conversation_id: str, total_message_count: int, older_messages: list, existing_summary: str | None
) -> str | None:
    if total_message_count < settings.HISTORY_SUMMARY_TRIGGER or not older_messages:
        return None

    conversation_text = "\n".join(f"{m.role.value}: {m.content}" for m in older_messages)
    if existing_summary:
        conversation_text = f"Previous summary: {existing_summary}\n\n{conversation_text}"

    model = get_chat_model(streaming=False)
    formatted = SUMMARIZE_HISTORY_PROMPT.invoke({"conversation_text": conversation_text})
    response = await model.ainvoke(formatted)
    return response.content
