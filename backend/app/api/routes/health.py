import redis.asyncio as redis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.rag.vector_store import get_qdrant_client

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Liveness probe: process is up. No dependency checks."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db), redis_client: redis.Redis = Depends(get_redis)):
    """Readiness probe: checks every downstream dependency the API needs
    to actually serve traffic. Used by orchestrators to gate traffic
    routing during rollout/rollback."""
    checks = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"error: {exc}"

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    try:
        get_qdrant_client().get_collections()
        checks["qdrant"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["qdrant"] = f"error: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ready" if healthy else "degraded", "checks": checks}
