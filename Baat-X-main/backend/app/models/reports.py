from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import GUID, Base, JSONBCompat, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import QueryCategory


class ReportSnapshot(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Materialised daily/weekly/monthly report.

    Snapshots are a cache only: they are always computed from real rows by the
    reports service and can be regenerated at any time.
    """

    __tablename__ = "report_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "period", "period_start", "user_id", name="uq_report_period"
        ),
        Index("ix_reports_business_period", "business_id", "period", "period_start"),
    )

    period: Mapped[str] = mapped_column(String(10), nullable=False)  # daily|weekly|monthly
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE")
    )
    metrics: Mapped[dict] = mapped_column(JSONBCompat, nullable=False)
    ai_insights: Mapped[list | None] = mapped_column(JSONBCompat)
    generated_by_model: Mapped[str | None] = mapped_column(String(80))


class ReportMetric(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Long, queryable metric series for charts and trend analysis."""

    __tablename__ = "report_metrics"
    __table_args__ = (
        UniqueConstraint("business_id", "metric_date", "metric_key", name="uq_metric_day_key"),
        Index("ix_metrics_business_date", "business_id", "metric_date"),
    )

    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class QueryCategoryStat(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "query_categories"
    __table_args__ = (
        UniqueConstraint("business_id", "stat_date", "category", name="uq_query_cat_day"),
        Index("ix_query_cat_business_date", "business_id", "stat_date"),
    )

    stat_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[QueryCategory] = mapped_column(String(32), nullable=False)
    count: Mapped[int] = mapped_column(default=0, nullable=False)
