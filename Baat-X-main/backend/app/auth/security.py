"""Password hashing and JWT issuance/verification."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.config.settings import get_settings
from app.core.errors import AuthenticationError, ValidationError

_hasher = PasswordHasher()
TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    settings = get_settings()
    if len(password) < settings.password_min_length:
        raise ValidationError(
            "password too short",
            user_message=f"Password must be at least {settings.password_min_length} characters.",
        )
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@dataclass(slots=True)
class TokenPayload:
    user_id: uuid.UUID
    business_id: uuid.UUID | None
    role: str | None
    token_type: TokenType
    token_version: int
    jti: str
    expires_at: datetime


def create_token(
    *,
    user_id: uuid.UUID,
    token_type: TokenType,
    business_id: uuid.UUID | None = None,
    role: str | None = None,
    token_version: int = 0,
) -> tuple[str, datetime]:
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    expires_at = now + ttl
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "typ": token_type,
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
        "iss": "baatx",
    }
    if business_id:
        claims["biz"] = str(business_id)
    if role:
        claims["role"] = role
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires_at


def decode_token(token: str, expected_type: TokenType) -> TokenPayload:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="baatx",
            options={"require": ["exp", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(
            "token expired", user_message="Your session expired. Please sign in again."
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("invalid token") from exc

    if claims.get("typ") != expected_type:
        raise AuthenticationError("wrong token type")

    return TokenPayload(
        user_id=uuid.UUID(claims["sub"]),
        business_id=uuid.UUID(claims["biz"]) if claims.get("biz") else None,
        role=claims.get("role"),
        token_type=expected_type,
        token_version=int(claims.get("tv", 0)),
        jti=claims["jti"],
        expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
    )
