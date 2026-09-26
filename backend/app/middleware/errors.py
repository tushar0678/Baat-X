"""Exception handlers producing the single ErrorResponse shape."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.logging import get_logger
from app.core.errors import BaatXError
from app.schemas.common import ErrorResponse

log = get_logger("errors")

FRIENDLY_HTTP: dict[int, str] = {
    400: "That request couldn't be understood. Please try again.",
    401: "Please sign in again.",
    403: "You don't have permission to do this.",
    404: "We couldn't find what you were looking for.",
    405: "That action isn't supported here.",
    409: "This action conflicts with existing data.",
    413: "That file is too large.",
    415: "This audio format isn't supported. Please select MP3, M4A, WAV, AAC, AMR, or OGG.",
    429: "You're going a bit fast. Please try again in a moment.",
    500: "Something went wrong. Please try again.",
    503: "This service is temporarily unavailable. Please try again shortly.",
}


def _respond(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details=None,
):
    payload = ErrorResponse(
        code=code,
        message=message,
        details=details,
        request_id=getattr(request.state, "request_id", None),
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )


def _safe_db_error_fields(exc: SQLAlchemyError) -> dict[str, str | None]:
    """Extract PostgreSQL diagnostics without logging SQL or parameter values."""
    original = getattr(exc, "orig", None)
    candidates = (
        original,
        getattr(original, "__cause__", None),
        getattr(original, "__context__", None),
    )

    constraint = None
    sqlstate = None
    database_error_type = None

    for candidate in candidates:
        if candidate is None:
            continue

        if database_error_type is None:
            database_error_type = type(candidate).__name__

        if constraint is None:
            constraint = getattr(candidate, "constraint_name", None)

        if sqlstate is None:
            sqlstate = (
                getattr(candidate, "sqlstate", None)
                or getattr(candidate, "pgcode", None)
            )

    return {
        "database_error_type": database_error_type,
        "constraint": constraint,
        "sqlstate": sqlstate,
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BaatXError)
    async def _baatx(request: Request, exc: BaatXError):
        if exc.status_code >= 500:
            log.warning("app_error", code=exc.code, status=exc.status_code)
        return _respond(
            request,
            exc.status_code,
            exc.code,
            exc.user_message,
            exc.details or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = sorted({str(e.get("loc", ["body"])[-1]) for e in exc.errors()})
        return _respond(
            request,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            "Some details are missing or invalid. Please check and try again.",
            {"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        message = FRIENDLY_HTTP.get(
            exc.status_code,
            "Something went wrong. Please try again.",
        )
        return _respond(
            request,
            exc.status_code,
            f"http_{exc.status_code}",
            message,
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        log.warning(
            "integrity_error",
            **_safe_db_error_fields(exc),
        )
        return _respond(
            request,
            409,
            "conflict",
            "This action conflicts with existing data.",
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db(request: Request, exc: SQLAlchemyError):
        log.error(
            "database_error",
            error=type(exc).__name__,
            **_safe_db_error_fields(exc),
        )
        return _respond(
            request,
            503,
            "database_unavailable",
            "We're having trouble reaching your data right now. Please try again shortly.",
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled_error", error=type(exc).__name__)
        return _respond(
            request,
            500,
            "internal_error",
            "Something went wrong. Please try again.",
        )