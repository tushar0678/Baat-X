from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config.logging import get_logger

log = get_logger("http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attaches a request id, binds log context and records latency."""

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN201
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, path=request.url.path, method=request.method
        )
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            log.exception("request_failed", duration_ms=_ms(started))
            raise
        response.headers["X-Request-Id"] = request_id
        if not request.url.path.startswith(("/health", "/ready", "/metrics")):
            log.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=_ms(started),
            )
        return response


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
