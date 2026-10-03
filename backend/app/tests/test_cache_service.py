import pytest
import fakeredis.aioredis as fakeredis

from app.services.cache_service import CacheService

pytestmark = pytest.mark.asyncio


async def test_cache_miss_then_hit():
    r = fakeredis.FakeRedis(decode_responses=True)
    cache = CacheService(r)

    assert await cache.get("repo-1", "abc123", "how does auth work?") is None

    await cache.set("repo-1", "abc123", "how does auth work?", {"answer": "...", "source_references": []})
    hit = await cache.get("repo-1", "abc123", "how does auth work?")
    assert hit is not None
    assert hit["answer"] == "..."


async def test_cache_key_is_normalized_and_case_insensitive():
    r = fakeredis.FakeRedis(decode_responses=True)
    cache = CacheService(r)

    await cache.set("repo-1", "abc123", "How does Auth work?", {"answer": "x", "source_references": []})
    hit = await cache.get("repo-1", "abc123", "  how does auth work?  ")
    assert hit is not None


async def test_cache_is_scoped_to_commit_sha():
    """A re-index that changes commit_sha must not serve stale answers."""
    r = fakeredis.FakeRedis(decode_responses=True)
    cache = CacheService(r)

    await cache.set("repo-1", "old_sha", "what does main.py do?", {"answer": "old", "source_references": []})
    assert await cache.get("repo-1", "new_sha", "what does main.py do?") is None


async def test_cache_invalidate_repository_clears_only_that_repo():
    r = fakeredis.FakeRedis(decode_responses=True)
    cache = CacheService(r)

    await cache.set("repo-1", "sha", "q1", {"answer": "a1", "source_references": []})
    await cache.set("repo-2", "sha", "q1", {"answer": "a2", "source_references": []})

    await cache.invalidate_repository("repo-1")

    assert await cache.get("repo-1", "sha", "q1") is None
    assert await cache.get("repo-2", "sha", "q1") is not None
