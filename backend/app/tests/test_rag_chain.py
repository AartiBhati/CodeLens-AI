from unittest.mock import AsyncMock, patch

import pytest

from app.rag.chain import run_rag_stream
from app.rag.prompts import NO_EVIDENCE_MESSAGE

pytestmark = pytest.mark.asyncio


async def test_returns_no_evidence_message_when_retrieval_is_empty():
    with patch("app.rag.chain.retrieve", return_value=[]):
        stream, result = await run_rag_stream(
            mode="ask_codebase",
            question="What does the nonexistent module do?",
            repository_id="repo-1",
            summary=None,
            history_rows=[],
        )
        tokens = [t async for t in stream]
        assert "".join(tokens) == NO_EVIDENCE_MESSAGE
        assert result.context_used is False
        assert result.source_references == []


async def test_returns_no_evidence_when_all_scores_below_threshold():
    low_score_chunks = [
        {"score": 0.05, "text": "irrelevant", "file_path": "a.py", "start_line": 1, "end_line": 2}
    ]
    with patch("app.rag.chain.retrieve", return_value=low_score_chunks):
        stream, result = await run_rag_stream(
            mode="ask_codebase",
            question="anything",
            repository_id="repo-1",
            summary=None,
            history_rows=[],
        )
        tokens = [t async for t in stream]
        assert "".join(tokens) == NO_EVIDENCE_MESSAGE
        assert result.context_used is False


async def test_source_references_deduplicated_and_sorted():
    chunks = [
        {"score": 0.9, "text": "a", "file_path": "b.py", "start_line": 1, "end_line": 5},
        {"score": 0.8, "text": "b", "file_path": "b.py", "start_line": 10, "end_line": 15},
        {"score": 0.7, "text": "c", "file_path": "a.py", "start_line": 1, "end_line": 5},
    ]
    mock_model = AsyncMock()

    async def fake_astream(_formatted):
        class Chunk:
            content = "answer token"
        yield Chunk()

    mock_model.astream = fake_astream

    with patch("app.rag.chain.retrieve", return_value=chunks), \
         patch("app.rag.chain.get_chat_model", return_value=mock_model):
        stream, result = await run_rag_stream(
            mode="ask_codebase",
            question="explain b.py",
            repository_id="repo-1",
            summary=None,
            history_rows=[],
        )
        _ = [t async for t in stream]
        assert result.source_references == ["a.py", "b.py"]
        assert result.context_used is True
