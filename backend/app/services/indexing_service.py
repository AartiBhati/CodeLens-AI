"""
Repository ingestion pipeline:

GitHub repo -> clone -> parse & language-detect -> smart chunk ->
metadata -> embed -> upsert into Qdrant

This module is transport-agnostic (no Kafka/DB imports) so it can be unit
tested directly and reused by both the async worker and, e.g., a future
manual re-index CLI.
"""
import time
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.chunking import chunk_file
from app.rag.embeddings import get_embedding_model
from app.rag.vector_store import ChunkMetadata, delete_repository_vectors, upsert_chunks
from app.utils.github_parser import ParsedRepository, clone_repository, parse_repository

logger = get_logger(__name__)


@dataclass
class IndexingResult:
    commit_sha: str
    primary_language: str | None
    chunk_count: int
    duration_ms: int


def index_repository(
    *, repository_id: str, project_id: str, github_url: str, branch: str
) -> IndexingResult:
    started = time.perf_counter()

    local_path = clone_repository(github_url, branch, repo_id=repository_id)
    parsed: ParsedRepository = parse_repository(local_path)

    # Remove any vectors from a previous commit before writing new ones,
    # so stale/deleted code never surfaces in retrieval.
    delete_repository_vectors(repository_id)

    embedder = get_embedding_model()
    total_chunks = 0
    batch_texts: list[str] = []
    batch_meta: list[ChunkMetadata] = []
    BATCH_SIZE = 64

    def flush():
        nonlocal total_chunks, batch_texts, batch_meta
        if not batch_texts:
            return
        vectors = embedder.embed_documents(batch_texts)
        total_chunks += upsert_chunks(vectors, batch_texts, batch_meta)
        batch_texts, batch_meta = [], []

    for file in parsed.files:
        language = _guess_language(file.path)
        for chunk in chunk_file(file.content, language):
            batch_texts.append(chunk.content)
            batch_meta.append(
                ChunkMetadata(
                    repository_id=repository_id,
                    project_id=project_id,
                    file_path=file.path,
                    language=language,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    commit_sha=parsed.commit_sha,
                    function_name=chunk.function_name,
                    class_name=chunk.class_name,
                )
            )
            if len(batch_texts) >= BATCH_SIZE:
                flush()
    flush()

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "repository_indexed",
        repository_id=repository_id,
        chunks=total_chunks,
        duration_ms=duration_ms,
        commit_sha=parsed.commit_sha,
    )

    return IndexingResult(
        commit_sha=parsed.commit_sha,
        primary_language=parsed.primary_language,
        chunk_count=total_chunks,
        duration_ms=duration_ms,
    )


def _guess_language(file_path: str) -> str | None:
    from app.utils.language_detect import EXTENSION_LANGUAGE_MAP
    from pathlib import Path

    return EXTENSION_LANGUAGE_MAP.get(Path(file_path).suffix.lower())
