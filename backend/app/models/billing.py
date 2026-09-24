from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import GUID, Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SubscriptionPlan


class Subscription(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("business_id", name="uq_subscription_business"),)

    plan: Mapped[SubscriptionPlan] = mapped_column(
        String(24), default=SubscriptionPlan.FREE, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    seats: Mapped[int] = mapped_column(default=1, nullable=False)
    monthly_minutes_quota: Mapped[int] = mapped_column(default=120, nullable=False)
    monthly_ai_requests_quota: Mapped[int] = mapped_column(default=500, nullable=False)
    current_period_start: Mapped[date | None] = mapped_column(Date)
    current_period_end: Mapped[date | None] = mapped_column(Date)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_reference: Mapped[str | None] = mapped_column(String(120))


class UsageRecord(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "usage"
    __table_args__ = (
        UniqueConstraint("business_id", "usage_date", "metric", name="uq_usage_day_metric"),
        Index("ix_usage_business_date", "business_id", "usage_date"),
    )

    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    quantity: Mapped[int] = mapped_column(default=0, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
