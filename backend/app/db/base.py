"""Declarative base + shared column mixins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator


class JSONBCompat(TypeDecorator):
    """JSONB on PostgreSQL, plain JSON elsewhere (sqlite in tests)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001, ANN201
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class GUID(TypeDecorator):
    """UUID on PostgreSQL, 36-char string elsewhere."""

    impl = PGUUID
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001, ANN201
        from sqlalchemy import String

        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSONBCompat, uuid.UUID: GUID}


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4, sort_order=-100
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, sort_order=100
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False, sort_order=101,
    )


class TenantMixin:
    """Every tenant-scoped row carries business_id. Repositories always filter on it."""

    business_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False, index=True, sort_order=-99,
    )
