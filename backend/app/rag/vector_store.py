"""
Thin wrapper around the Qdrant client for the single
`repository_embeddings` collection. Every point's payload carries the
metadata needed for filtering (repository_id, file_path, etc.) and for
attaching source references to the final answer.
"""
import uuid
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChunkMetadata:
    repository_id: str
    project_id: str
    file_path: str
    language: str | None
    start_line: int
    end_line: int
    commit_sha: str
    function_name: str | None = None
    class_name: str | None = None


@lru_cache
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def ensure_collection() -> None:
    client = get_qdrant_client()
    existing = {c.name for c in client.get_collections().collections}
    if settings.QDRANT_COLLECTION in existing:
        info = client.get_collection(settings.QDRANT_COLLECTION)
        vectors_cfg = info.config.params.vectors
        existing_dim = getattr(vectors_cfg, "size", None)
        if existing_dim is not None and existing_dim != settings.EMBEDDING_DIM:
            raise ValueError(
                f"Qdrant collection '{settings.QDRANT_COLLECTION}' has {existing_dim}-dim vectors "
                f"but EMBEDDING_DIM={settings.EMBEDDING_DIM}. You switched embedding models: "
                f"delete the old collection (e.g. `docker compose down -v` or "
                f"`curl -X DELETE http://localhost:6333/collections/{settings.QDRANT_COLLECTION}`) "
                f"and re-index your repositories."
            )
        return
    client.create_collection(
        collection_name=settings.QDRANT_COLLECTION,
        vectors_config=qmodels.VectorParams(
            size=settings.EMBEDDING_DIM, distance=qmodels.Distance.COSINE
        ),
    )
    # Payload indexes make metadata-filtered search fast at scale.
    for field_name in ("repository_id", "project_id", "file_path", "language"):
        client.create_payload_index(
            collection_name=settings.QDRANT_COLLECTION,
            field_name=field_name,
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
    logger.info("qdrant_collection_created", collection=settings.QDRANT_COLLECTION)


def upsert_chunks(vectors: list[list[float]], texts: list[str], metadatas: list[ChunkMetadata]) -> int:
    ensure_collection()
    if vectors and len(vectors[0]) != settings.EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch: model produced {len(vectors[0])}-dim vectors but "
            f"EMBEDDING_DIM is set to {settings.EMBEDDING_DIM}. BAAI/bge-small-en-v1.5 is 384-dim, "
            f"Gemini's text-embedding-004 is 768-dim, OpenAI's text-embedding-3-small is 1536-dim. "
            f"Update EMBEDDING_DIM in your .env to match the active model, then re-run indexing."
        )
    client = get_qdrant_client()
    points = [
        qmodels.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={"text": text, **metadata.__dict__},
        )
        for vector, text, metadata in zip(vectors, texts, metadatas, strict=True)
    ]
    client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
    return len(points)


def delete_repository_vectors(repository_id: str) -> None:
    """Called before re-indexing so stale chunks from a previous commit
    don't linger and pollute retrieval."""
    client = get_qdrant_client()
    ensure_collection()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="repository_id", match=qmodels.MatchValue(value=repository_id))]
            )
        ),
    )
    logger.info("qdrant_vectors_deleted", repository_id=repository_id)


def similarity_search(
    query_vector: list[float],
    repository_id: str,
    top_k: int,
    file_path_contains: str | None = None,
) -> list[dict]:
    client = get_qdrant_client()
    ensure_collection()

    must_conditions = [
        qmodels.FieldCondition(key="repository_id", match=qmodels.MatchValue(value=repository_id))
    ]
    if file_path_contains:
        must_conditions.append(
            qmodels.FieldCondition(key="file_path", match=qmodels.MatchText(text=file_path_contains))
        )

    results = client.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=query_vector,
        query_filter=qmodels.Filter(must=must_conditions),
        limit=top_k,
        with_payload=True,
    )
    return [{"score": r.score, **r.payload} for r in results]
