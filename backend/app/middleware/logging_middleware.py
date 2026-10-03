import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_logger

logger = get_logger("http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()

        response = await call_next(request)

        latency_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
        structlog.contextvars.clear_contextvars()
        return response
