from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.enums import QueryCategory
from app.models.reports import QueryCategoryStat, ReportMetric, ReportSnapshot
from app.repositories.base import TenantRepository


class ReportRepository(TenantRepository[ReportSnapshot]):
    model = ReportSnapshot

    async def get_snapshot(self, period: str, period_start: date) -> ReportSnapshot | None:
        stmt = (
            self.base_query()
            .where(ReportSnapshot.period == period)
            .where(ReportSnapshot.period_start == period_start)
            .where(ReportSnapshot.user_id.is_(None))
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def upsert_snapshot(
        self,
        *,
        period: str,
        period_start: date,
        period_end: date,
        metrics: dict,
        ai_insights: list[str] | None,
        model_name: str | None,
    ) -> ReportSnapshot:
        snapshot = await self.get_snapshot(period, period_start)
        if snapshot is None:
            snapshot = ReportSnapshot(
                business_id=self.business_id,
                period=period,
                period_start=period_start,
                period_end=period_end,
                metrics=metrics,
                ai_insights=ai_insights,
                generated_by_model=model_name,
            )
            self.session.add(snapshot)
        else:
            snapshot.metrics = metrics
            snapshot.ai_insights = ai_insights
            snapshot.period_end = period_end
            snapshot.generated_by_model = model_name
        return snapshot

    async def bump_query_category(self, stat_date: date, category: QueryCategory) -> None:
        dialect = self.session.bind.dialect.name if self.session.bind else "postgresql"
        if dialect == "postgresql":
            stmt = (
                pg_insert(QueryCategoryStat)
                .values(
                    business_id=self.business_id,
                    stat_date=stat_date,
                    category=category,
                    count=1,
                )
                .on_conflict_do_update(
                    index_elements=["business_id", "stat_date", "category"],
                    set_={"count": QueryCategoryStat.count + 1},
                )
            )
            await self.session.execute(stmt)
            return

        existing = (
            await self.session.execute(
                select(QueryCategoryStat).where(
                    QueryCategoryStat.business_id == self.business_id,
                    QueryCategoryStat.stat_date == stat_date,
                    QueryCategoryStat.category == category,
                )
            )
        ).scalars().first()
        if existing:
            existing.count += 1
        else:
            self.session.add(
                QueryCategoryStat(
                    business_id=self.business_id,
                    stat_date=stat_date,
                    category=category,
                    count=1,
                )
            )

    async def query_category_counts(self, start: date, end: date) -> dict[QueryCategory, int]:
        stmt = (
            select(QueryCategoryStat.category, func.sum(QueryCategoryStat.count))
            .where(QueryCategoryStat.business_id == self.business_id)
            .where(QueryCategoryStat.stat_date >= start)
            .where(QueryCategoryStat.stat_date <= end)
            .group_by(QueryCategoryStat.category)
        )
        rows = (await self.session.execute(stmt)).all()
        return {QueryCategory(cat): int(total or 0) for cat, total in rows}

    async def record_metric(self, metric_date: date, key: str, value: float) -> None:
        existing = (
            await self.session.execute(
                select(ReportMetric).where(
                    ReportMetric.business_id == self.business_id,
                    ReportMetric.metric_date == metric_date,
                    ReportMetric.metric_key == key,
                )
            )
        ).scalars().first()
        if existing:
            existing.metric_value = value
        else:
            self.session.add(
                ReportMetric(
                    business_id=self.business_id,
                    metric_date=metric_date,
                    metric_key=key,
                    metric_value=value,
                )
            )
