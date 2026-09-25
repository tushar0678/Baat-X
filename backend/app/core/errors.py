"""Application errors -> consistent, human-friendly API responses.

The `user_message` is what the Android app shows verbatim; `code` is what
clients branch on. We never surface stack traces or driver errors.
"""

from __future__ import annotations

from typing import Any


class BaatXError(Exception):
    status_code = 500
    code = "internal_error"
    user_message = "Something went wrong. Please try again."

    def __init__(
        self,
        message: str | None = None,
        *,
        user_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.user_message)
        self.message = message or self.user_message
        if user_message:
            self.user_message = user_message
        self.details = details or {}


class NotFoundError(BaatXError):
    status_code = 404
    code = "not_found"
    user_message = "We couldn't find what you were looking for."


class ValidationError(BaatXError):
    status_code = 422
    code = "validation_error"
    user_message = "Some details are missing or invalid. Please check and try again."


class ConflictError(BaatXError):
    status_code = 409
    code = "conflict"
    user_message = "This action conflicts with existing data."


class AuthenticationError(BaatXError):
    status_code = 401
    code = "unauthenticated"
    user_message = "Please sign in again."


class PermissionError_(BaatXError):
    status_code = 403
    code = "forbidden"
    user_message = "You don't have permission to do this."


# Alias used by the multi-organization authorization layer (deps.py, rbac.py,
# and the scoped endpoints). Kept as a plain alias - not a subclass - so
# `isinstance(exc, PermissionError_)` and `isinstance(exc, AuthorizationError)`
# are both true for the same exception, and the existing FastAPI exception
# handler (registered for `PermissionError_`) catches it without needing a
# second handler registration.
AuthorizationError = PermissionError_


class TenantIsolationError(PermissionError_):
    code = "tenant_isolation"
    user_message = "You don't have access to this record."


class RateLimitError(BaatXError):
    status_code = 429
    code = "rate_limited"
    user_message = "You're going a bit fast. Please try again in a moment."


class UnsupportedAudioError(BaatXError):
    status_code = 415
    code = "unsupported_audio"
    user_message = (
        "This audio format isn't supported. Please select MP3, M4A, WAV, AAC, AMR, or OGG."
    )


class AudioTooLargeError(BaatXError):
    status_code = 413
    code = "audio_too_large"
    user_message = "This recording is too large to upload. Please try a shorter recording."


class AIProcessingError(BaatXError):
    status_code = 502
    code = "ai_processing_failed"
    user_message = "Something went wrong while processing your recording. Please try again."


class ProviderUnavailableError(BaatXError):
    status_code = 503
    code = "provider_unavailable"
    user_message = "This service is temporarily unavailable. Please try again shortly."


class QuotaExceededError(BaatXError):
    status_code = 402
    code = "quota_exceeded"
    user_message = "You've used up your plan's AI quota for this month."


class ApprovalRequiredError(BaatXError):
    status_code = 409
    code = "approval_required"
    user_message = "This message must be reviewed and approved before it can be sent."