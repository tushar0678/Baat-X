"""Redis-backed fixed-window rate limiting, keyed per tenant/user and route group.

Falls back to allowing traffic if Redis is unavailable - availability of the CRM
matters more than perfect throttling, and the platform ingress also limits.
"""

from __future__ import annotations

import time

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config.logging import get_logger
from app.schemas.common import ErrorResponse

log = get_logger("ratelimit")

EXEMPT_PREFIXES = ("/health", "/ready", "/docs", "/openapi.json", "/redoc")


def _parse(rule: str) -> tuple[int, int]:
    count, _, unit = rule.partition("/")
    seconds = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}.get(unit.strip(), 60)
    return int(count), seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, default_rule: str, ai_rule: str, auth_rule: str) -> None:  # noqa: ANN001
        super().__init__(app)
        self._default = _parse(default_rule)
        self._ai = _parse(ai_rule)
        self._auth = _parse(auth_rule)

    def _rule_for(self, path: str) -> tuple[int, int, str]:
        if "/ai/" in path or "/assistant/" in path:
            return (*self._ai, "ai")
        if "/auth/" in path:
            return (*self._auth, "auth")
        return (*self._default, "default")

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN201
        redis: Redis | None = getattr(request.app.state, "redis", None)
        if redis is None or request.url.path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        limit, window, group = self._rule_for(request.url.path)
        identity = (
            request.headers.get("X-Business-Id")
            or request.headers.get("Authorization", "")[-24:]
            or (request.client.host if request.client else "anonymous")
        )
        key = f"rl:{group}:{identity}:{int(time.time() // window)}"

        try:
            pipeline = redis.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, window + 5)
            current, _ = await pipeline.execute()
        except Exception:  # noqa: BLE001 - never fail a request because of the limiter
            return await call_next(request)

        if int(current) > limit:
            body = ErrorResponse(
                code="rate_limited",
                message="You're going a bit fast. Please try again in a moment.",
                request_id=getattr(request.state, "request_id", None),
            )
            return JSONResponse(
                status_code=429,
                content=body.model_dump(mode="json"),
                headers={"Retry-After": str(window - int(time.time() % window))},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - int(current)))
        return response
