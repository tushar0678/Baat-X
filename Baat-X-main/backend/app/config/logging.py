"""Structured, privacy-aware logging.

Hard rule: raw audio, transcripts, passwords, tokens and API keys must never be
logged. `_redact` enforces that centrally so a careless call site cannot leak.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

SENSITIVE_KEYS = {
    "password", "passwd", "secret", "token", "access_token", "refresh_token",
    "authorization", "api_key", "apikey", "jwt_secret", "connection_string",
    "audio", "audio_bytes", "raw_audio", "transcript", "transcript_text",
    "source_text", "phone", "normalized_phone", "email",
}
REDACTED = "[redacted]"


def _redact(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = REDACTED
    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    for noisy in ("uvicorn.access", "azure.core.pipeline.policies.http_logging_policy"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _redact,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
