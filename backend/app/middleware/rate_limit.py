import redis.asyncio as redis
from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user, get_redis
from app.models.user import User
from app.services.rate_limiter import RateLimitExceeded, RateLimiter


async def enforce_rate_limit(
    user: User = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis),
) -> None:
    limiter = RateLimiter(redis_client)
    try:
        await limiter.check(str(user.id))
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
