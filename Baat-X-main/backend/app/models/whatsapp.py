from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import GUID, Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WhatsAppMessageStatus


class WhatsAppMessage(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Every outbound message starts as a DRAFT and needs explicit human approval."""

    __tablename__ = "whatsapp_messages"
    __table_args__ = (Index("ix_wa_business_status", "business_id", "status"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[WhatsAppMessageStatus] = mapped_column(
        String(16), default=WhatsAppMessageStatus.DRAFT, nullable=False
    )
    drafted_by_ai: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(400))
