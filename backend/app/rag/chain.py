"""
The core RAG chain, built with LangChain Expression Language (LCEL).

retrieve() -> build context string -> format prompt -> stream from chat model

Kept as plain functions/generators (rather than a single opaque `.invoke()`)
so the API layer can persist source references and the final assembled
answer after streaming completes.
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage

from app.core.logging import get_logger
from app.rag.llm import get_chat_model
from app.rag.prompts import NO_EVIDENCE_MESSAGE, PROMPT_REGISTRY
from app.rag.retriever import retrieve

logger = get_logger(__name__)

MIN_RELEVANCE_SCORE = 0.15  # below this, we treat retrieval as "no evidence"


@dataclass
class RagResult:
    context_used: bool
    source_references: list[str]
    chunks: list[dict]


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        header = f"# {c['file_path']} (lines {c['start_line']}-{c['end_line']})"
        if c.get("function_name"):
            header += f" function `{c['function_name']}`"
        if c.get("class_name"):
            header += f" class `{c['class_name']}`"
        parts.append(f"{header}\n{c['text']}")
    return "\n\n---\n\n".join(parts)


def _history_to_messages(history_rows: list) -> list:
    messages = []
    for m in history_rows:
        if m.role.value == "user":
            messages.append(HumanMessage(content=m.content))
        elif m.role.value == "assistant":
            messages.append(AIMessage(content=m.content))
    return messages


async def run_rag_stream(
    *,
    mode: str,
    question: str,
    repository_id: str,
    summary: str | None,
    history_rows: list,
    file_path: str | None = None,
) -> tuple[AsyncIterator[str], RagResult]:
    """Runs retrieval synchronously (fast, local network call to Qdrant),
    then returns an async token stream from the LLM plus the retrieval
    metadata needed to persist source references."""

    chunks = retrieve(
        question=question,
        repository_id=repository_id,
        file_path_contains=file_path,
    )
    relevant_chunks = [c for c in chunks if c["score"] >= MIN_RELEVANCE_SCORE]

    if not relevant_chunks:
        async def _no_evidence_stream():
            yield NO_EVIDENCE_MESSAGE

        return _no_evidence_stream(), RagResult(context_used=False, source_references=[], chunks=[])

    context = _build_context(relevant_chunks)
    prompt_template = PROMPT_REGISTRY.get(mode, PROMPT_REGISTRY["ask_codebase"])
    model = get_chat_model(streaming=True)

    prompt_kwargs = {
        "context": context,
        "question": question,
        "summary": summary or "None yet.",
        "history": _history_to_messages(history_rows),
        "file_path": file_path or "",
    }
    # Prompts that don't use every placeholder simply ignore extras.
    formatted = prompt_template.invoke(
        {k: v for k, v in prompt_kwargs.items() if k in prompt_template.input_variables}
    )

    chain = model

    async def _token_stream():
        async for event in chain.astream(formatted):
            content = getattr(event, "content", "")
            if content:
                yield content

    source_refs = sorted({c["file_path"] for c in relevant_chunks})
    return _token_stream(), RagResult(context_used=True, source_references=source_refs, chunks=relevant_chunks)
