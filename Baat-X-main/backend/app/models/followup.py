from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import GUID, Base, JSONBCompat, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import FollowUpStatus, FollowUpType, NotificationType, TaskStatus


class FollowUp(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "follow_ups"
    __table_args__ = (
        Index("ix_followups_business_due_status", "business_id", "due_at", "status"),
        Index("ix_followups_business_customer", "business_id", "customer_id"),
        Index("ix_followups_assignee_due", "assigned_user_id", "due_at"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("ai_processing_jobs.id", ondelete="SET NULL")
    )
    type: Mapped[FollowUpType] = mapped_column(
        String(32), default=FollowUpType.GENERAL_FOLLOW_UP, nullable=False
    )
    status: Mapped[FollowUpStatus] = mapped_column(
        String(24), default=FollowUpStatus.PENDING, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    due_time_known: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by_ai: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rescheduled_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_requested_callback: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


class Task(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Internal to-do not tied to a customer commitment."""

    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_business_status_due", "business_id", "status", "due_at"),)

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(String(16), default=TaskStatus.OPEN, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by_ai: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        # Dedupe key stops notification spam for the same entity + type + day.
        Index("ix_notifications_dedupe", "business_id", "dedupe_key", unique=True),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="CASCADE")
    )
    follow_up_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("follow_ups.id", ondelete="CASCADE")
    )
    type: Mapped[NotificationType] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONBCompat)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
