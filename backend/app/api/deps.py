from collections.abc import AsyncGenerator
from uuid import UUID

import redis.asyncio as redis
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")

_redis_pool: redis.Redis | None = None


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield _redis_pool


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if user_id is None or jti is None:
        raise credentials_exception

    async for r in get_redis():
        if await r.get(f"blacklist:{jti}"):
            raise credentials_exception
        break

    user = await UserRepository(db).get_by_id(UUID(user_id))
    if user is None or not user.is_active:
        raise credentials_exception
    return user
