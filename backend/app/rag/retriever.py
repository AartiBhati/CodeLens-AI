"""
Retrieval step of the RAG pipeline: embed the question, run a
metadata-filtered similarity search against Qdrant, then apply a cheap
lexical-overlap rerank on top of the vector score so exact identifier
matches (e.g. a function name typed verbatim) outrank purely-semantic
near-misses.
"""
import re

from app.core.config import settings
from app.rag.embeddings import get_embedding_model
from app.rag.vector_store import similarity_search


def _lexical_overlap_boost(query: str, text: str) -> float:
    query_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query.lower()))
    text_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower()))
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens) / len(query_tokens)
    return overlap * 0.15  # small boost; vector similarity still dominates


def retrieve(
    question: str,
    repository_id: str,
    top_k: int | None = None,
    file_path_contains: str | None = None,
) -> list[dict]:
    top_k = top_k or settings.RETRIEVAL_TOP_K
    embedder = get_embedding_model()
    query_vector = embedder.embed_query(question)

    # Over-fetch, then rerank and truncate to top_k.
    candidates = similarity_search(
        query_vector=query_vector,
        repository_id=repository_id,
        top_k=top_k * 3,
        file_path_contains=file_path_contains,
    )

    for c in candidates:
        c["rerank_score"] = c["score"] + _lexical_overlap_boost(question, c.get("text", ""))

    candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
    return candidates[:top_k]
