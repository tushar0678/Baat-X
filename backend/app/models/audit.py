from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import GUID, Base, JSONBCompat, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Append-only trail of security/CRM-relevant actions.

    `metadata_json` must contain identifiers and outcomes only - never customer
    content, transcripts or secrets.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_business_created", "business_id", "created_at"),
        Index("ix_audit_business_action", "business_id", "action"),
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(48))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    result: Mapped[str] = mapped_column(String(16), default="success", nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict | None] = mapped_column(JSONBCompat)
