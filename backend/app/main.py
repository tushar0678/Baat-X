"""BaatX API.

You talk. BaatX remembers, updates, and reminds.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from redis.asyncio import Redis
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings
from app.db.session import dispose_engine
from app.middleware.errors import register_exception_handlers
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.ai.factory import close_providers
from app.workers.queue import close_pool

log = get_logger("app")

DESCRIPTION = """
BaatX turns a conversation into CRM data.

**Privacy:** we don't store your recordings. Audio is uploaded to private storage,
processed, and deleted - we keep only the structured business information you approve.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log.info("api_starting", environment=settings.environment)

    redis: Redis | None = None
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis.ping()
    except Exception:  # noqa: BLE001 - rate limiting degrades, the API still serves
        log.warning("redis_unavailable_rate_limiting_disabled")
        redis = None
    app.state.redis = redis

    if settings.applicationinsights_connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(
                connection_string=settings.applicationinsights_connection_string
            )
            log.info("app_insights_enabled")
        except Exception:  # noqa: BLE001
            log.warning("app_insights_setup_failed")

    yield

    if redis is not None:
        await redis.aclose()
    await close_pool()
    await close_providers()
    await dispose_engine()
    log.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="BaatX API",
        description=DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Business-Id", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )
    # The limiter reads app.state.redis lazily, so it degrades to pass-through
    # when Redis is unavailable instead of taking the API down.
    app.add_middleware(
        RateLimitMiddleware,
        default_rule=settings.rate_limit_default,
        ai_rule=settings.rate_limit_ai,
        auth_rule=settings.rate_limit_auth,
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
