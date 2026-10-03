from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair, UserLogin, UserRegister


class AuthService:
    def __init__(self, db: AsyncSession, redis_client: redis.Redis):
        self.db = db
        self.redis = redis_client
        self.users = UserRepository(db)

    async def register(self, payload: UserRegister) -> User:
        existing = await self.users.get_by_email(payload.email)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        user = await self.users.create(
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
        )
        await self.db.commit()
        return user

    async def login(self, payload: UserLogin) -> TokenPair:
        user = await self.users.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
            )
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

        return TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def logout(self, token: str) -> None:
        """Invalidation strategy: JWTs are stateless, so we blacklist the
        token's jti in Redis for exactly its remaining lifetime. Cheaper than
        a DB-backed session table, self-cleans via TTL, and works across
        multiple API replicas."""
        payload = decode_token(token)
        if not payload:
            return
        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            return

        ttl = int(exp - datetime.now(timezone.utc).timestamp())
        if ttl > 0:
            await self.redis.set(f"blacklist:{jti}", "1", ex=ttl)
