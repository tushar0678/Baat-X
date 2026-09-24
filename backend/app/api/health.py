from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.config.settings import get_settings
from app.db.session import get_sessionmaker
from app.schemas.common import HealthResponse, ReadinessResponse
from app.workers.queue import queue_healthy

router = APIRouter(tags=["System"])
VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", version=VERSION, environment=settings.environment)


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready(response: Response) -> ReadinessResponse:
    database = "ok"
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database = "unavailable"

    queue = "ok" if await queue_healthy() else "unavailable"
    if database != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if database == "ok" else "not_ready", database=database, queue=queue
    )
