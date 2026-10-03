"""
AI response cache.

Repeated questions against the same repository at the same commit are
extremely common (multiple teammates asking "what does auth do") so we cache
the final answer keyed on (repository_id, commit_sha, normalized question).
Cache is explicitly invalidated whenever the repository is re-indexed, since
a new commit can change the correct answer.
"""
import hashlib
import json

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _cache_key(repository_id: str, commit_sha: str | None, question: str) -> str:
    normalized = question.strip().lower()
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"ai_cache:{repository_id}:{commit_sha or 'unindexed'}:{digest}"


class CacheService:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def get(self, repository_id: str, commit_sha: str | None, question: str) -> dict | None:
        key = _cache_key(repository_id, commit_sha, question)
        raw = await self.redis.get(key)
        if raw is None:
            return None
        logger.info("cache_hit", key=key)
        return json.loads(raw)

    async def set(
        self, repository_id: str, commit_sha: str | None, question: str, answer: dict
    ) -> None:
        key = _cache_key(repository_id, commit_sha, question)
        await self.redis.set(key, json.dumps(answer), ex=settings.REDIS_CACHE_TTL_SECONDS)

    async def invalidate_repository(self, repository_id: str) -> None:
        """Called by the indexing worker after a successful re-index."""
        pattern = f"ai_cache:{repository_id}:*"
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await self.redis.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                await self.redis.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        logger.info("cache_invalidated", repository_id=repository_id, keys_deleted=deleted)
