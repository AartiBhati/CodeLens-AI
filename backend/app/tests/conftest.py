"""
Shared pytest fixtures.

Note: the schema uses PostgreSQL-native column types (UUID, JSONB, ARRAY),
which do not compile against SQLite -- so these tests run against a real
Postgres instance rather than an in-memory DB. Set TEST_DATABASE_URL to
point at a disposable database (the Jenkinsfile spins up `postgres` +
`redis` via `docker compose` before the pytest stage; see Jenkinsfile).
Redis-backed services (cache, rate limiter, blacklist) use fakeredis so
those don't need a real server. Kafka and Qdrant calls are mocked at the
boundary since they're external I/O, not business logic under test here.
"""
import os
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import deps as api_deps
from app.db.base import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://codelens:codelens@localhost:5432/codelens_test",
)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        # Fresh schema per test module run; fine for a disposable test DB.
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_local = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_local() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    async def _override_get_db():
        yield db_session

    import fakeredis.aioredis as fakeredis

    fake_redis = fakeredis.FakeRedis(decode_responses=True)

    async def _override_get_redis():
        yield fake_redis

    app.dependency_overrides[api_deps.get_db] = _override_get_db
    app.dependency_overrides[api_deps.get_redis] = _override_get_redis

    with patch("app.workers.kafka_producer.publish_event") as mock_publish:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.mock_publish_event = mock_publish  # convenience handle for assertions
            yield client

    app.dependency_overrides.clear()
