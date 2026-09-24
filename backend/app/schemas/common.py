from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Every non-2xx response has exactly this shape."""

    code: str
    message: str           # human-friendly, safe to show to the user
    details: dict[str, Any] | None = None
    request_id: str | None = None


class OkResponse(BaseModel):
    ok: bool = True
    message: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    queue: str
