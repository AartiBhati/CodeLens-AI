import redis.asyncio as redis
from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis, oauth2_scheme
from app.models.user import User
from app.schemas.auth import TokenPair, UserLogin, UserOut, UserRegister
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserRegister,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    service = AuthService(db, redis_client)
    user = await service.register(payload)
    return user


@router.post("/login", response_model=TokenPair)
async def login(
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    service = AuthService(db, redis_client)
    return await service.login(payload)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    service = AuthService(db, redis_client)
    await service.logout(token)
