"""Fixed-window rate limiter for the AI endpoint, backed by Redis INCR + TTL.

Simple and cheap: one INCR per request, key expires automatically at the
window boundary. Good enough for per-user-per-minute limiting; a sliding-window
or token-bucket algorithm would be a drop-in upgrade if burst behavior at the
window edge becomes a problem.
"""
import time

import redis.asyncio as redis

from app.core.config import settings


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")


class RateLimiter:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def check(self, user_id: str, limit: int | None = None) -> None:
        limit = limit or settings.RATE_LIMIT_REQUESTS_PER_MINUTE
        window = int(time.time() // 60)
        key = f"rate_limit:{user_id}:{window}"

        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, 60)

        if current > limit:
            ttl = await self.redis.ttl(key)
            raise RateLimitExceeded(retry_after=max(ttl, 1))
