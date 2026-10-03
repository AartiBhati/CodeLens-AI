import pytest
import fakeredis.aioredis as fakeredis

from app.services.rate_limiter import RateLimitExceeded, RateLimiter

pytestmark = pytest.mark.asyncio


async def test_rate_limiter_allows_up_to_limit():
    r = fakeredis.FakeRedis(decode_responses=True)
    limiter = RateLimiter(r)
    for _ in range(5):
        await limiter.check("user-1", limit=5)  # should not raise


async def test_rate_limiter_blocks_over_limit():
    r = fakeredis.FakeRedis(decode_responses=True)
    limiter = RateLimiter(r)
    for _ in range(3):
        await limiter.check("user-2", limit=3)

    with pytest.raises(RateLimitExceeded) as exc_info:
        await limiter.check("user-2", limit=3)
    assert exc_info.value.retry_after > 0


async def test_rate_limiter_is_per_user():
    r = fakeredis.FakeRedis(decode_responses=True)
    limiter = RateLimiter(r)
    for _ in range(3):
        await limiter.check("user-a", limit=3)

    # A different user should have an independent budget.
    await limiter.check("user-b", limit=3)
