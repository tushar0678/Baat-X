"""Reports and dashboard.

Every number here is a COUNT/SUM over real rows (§43). The only generated text
is `ai_insights`, which is computed from those same numbers and is always
labelled `insights_are_ai_generated = true`.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging import get_logger
from app.models.conversation import AIProcessingJob, ConversationEvent
from app.models.crm import Customer, Lead, LeadStatusTransition
from app.models.enums import JobStatus, LeadStatus, QueryCategory
from app.models.followup import FollowUp
from app.repositories.customer_repo import CustomerRepository
from app.repositories.followup_repo import ACTIVE_STATUSES, FollowUpRepository
from app.repositories.job_repo import ConversationEventRepository
from app.repositories.lead_repo import LeadRepository
from app.repositories.report_repo import ReportRepository
from app.schemas.report import (
    AIActivityItem,
    DailyReportResponse,
    DashboardConversions,
    DashboardResponse,
    DashboardToday,
    FollowUpMetrics,
    ImportantFollowUp,
    LeadMetrics,
    PeriodReportResponse,
    QueryMetrics,
)
from app.services.ai.base import LLMProvider
from app.services.ai.prompts import INSIGHTS_SYSTEM_PROMPT

log = get_logger(__name__)

PRICE_CONCERN_CATEGORIES = (QueryCategory.PRICING, QueryCategory.DISCOUNT)


@dataclass(slots=True)
class Window:
    """Half-open [start, end) interval.

    Bounds are normalised to UTC because every timestamp column is stored in UTC;
    the local business day is decided by the tenant timezone before conversion.
    """

    start: datetime
    end: datetime
    start_date: date
    end_date: date

    @classmethod
    def of(cls, start: datetime, end: datetime, start_date: date, end_date: date) -> "Window":
        return cls(start.astimezone(UTC), end.astimezone(UTC), start_date, end_date)


class ReportService:
    def __init__(
        self,
        session: AsyncSession,
        business_id: uuid.UUID,
        *,
        timezone: str = "Asia/Kolkata",
        llm: LLMProvider | None = None,
    ) -> None:
        self.session = session
        self.business_id = business_id
        self.tz = ZoneInfo(timezone)
        self.llm = llm
        self.customers = CustomerRepository(session, business_id)
        self.leads = LeadRepository(session, business_id)
        self.follow_ups = FollowUpRepository(session, business_id)
        self.events = ConversationEventRepository(session, business_id)
        self.reports = ReportRepository(session, business_id)

    # ---------------- windows ----------------
    def day_window(self, day: date) -> Window:
        start = datetime.combine(day, time.min, tzinfo=self.tz)
        return Window.of(start, start + timedelta(days=1), day, day)

    def week_window(self, any_day: date) -> Window:
        start_date = any_day - timedelta(days=any_day.weekday())  # Monday
        start = datetime.combine(start_date, time.min, tzinfo=self.tz)
        return Window.of(
            start, start + timedelta(days=7), start_date, start_date + timedelta(days=6)
        )

    def month_window(self, any_day: date) -> Window:
        start_date = any_day.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1)
        start = datetime.combine(start_date, time.min, tzinfo=self.tz)
        end = datetime.combine(end_date, time.min, tzinfo=self.tz)
        return Window.of(start, end, start_date, end_date - timedelta(days=1))

    # ---------------- primitives ----------------
    async def _count(self, stmt) -> int:  # noqa: ANN001
        return int((await self.session.execute(stmt)).scalar_one())

    async def _new_customers(self, w: Window) -> int:
        return await self._count(
            select(func.count())
            .select_from(Customer)
            .where(Customer.business_id == self.business_id)
            .where(Customer.created_at >= w.start)
            .where(Customer.created_at < w.end)
        )

    async def _new_leads(self, w: Window) -> int:
        return await self._count(
            select(func.count())
            .select_from(Lead)
            .where(Lead.business_id == self.business_id)
            .where(Lead.created_at >= w.start)
            .where(Lead.created_at < w.end)
        )

    async def _customers_in_status(self, w: Window, status: LeadStatus) -> int:
        """Customers that entered this status at any point during the window."""
        return await self._count(
            select(func.count(func.distinct(Lead.customer_id)))
            .select_from(LeadStatusTransition)
            .join(Lead, Lead.id == LeadStatusTransition.lead_id)
            .where(LeadStatusTransition.business_id == self.business_id)
            .where(LeadStatusTransition.to_status == status)
            .where(LeadStatusTransition.created_at >= w.start)
            .where(LeadStatusTransition.created_at < w.end)
        )

    async def _follow_up_metrics(self, w: Window, now: datetime) -> FollowUpMetrics:
        return FollowUpMetrics(
            created=await self.follow_ups.count_created(w.start, w.end),
            completed=await self.follow_ups.count_completed(w.start, w.end),
            pending=await self.follow_ups.count_pending(now),
            overdue=await self.follow_ups.count_overdue(now),
        )

    async def _query_metrics(self, w: Window) -> QueryMetrics:
        by_category = await self.reports.query_category_counts(w.start_date, w.end_date)
        return QueryMetrics(
            total_queries=sum(by_category.values()),
            by_category=by_category,
            quotations_requested=by_category.get(QueryCategory.QUOTATION, 0)
            + await self.follow_ups.count_quotations_promised(w.start, w.end),
            price_concerns=sum(by_category.get(c, 0) for c in PRICE_CONCERN_CATEGORIES),
            callbacks_requested=await self.follow_ups.count_callbacks_requested(w.start, w.end),
            availability_queries=by_category.get(QueryCategory.AVAILABILITY, 0),
        )

    async def _important_follow_ups(self, now: datetime, limit: int = 5) -> list[ImportantFollowUp]:
        stmt = (
            select(FollowUp, Customer.name)
            .join(Customer, Customer.id == FollowUp.customer_id)
            .where(FollowUp.business_id == self.business_id)
            .where(FollowUp.status.in_(ACTIVE_STATUSES))
            .order_by(FollowUp.due_at.asc())
            .limit(limit)
        )
        return [
            ImportantFollowUp(
                customer_id=follow_up.customer_id,
                customer_name=name,
                action=follow_up.title,
                due_at=follow_up.due_at,
            )
            for follow_up, name in (await self.session.execute(stmt)).all()
        ]

    # ---------------- dashboard ----------------
    async def dashboard(self, *, user_id: uuid.UUID | None, restrict: bool) -> DashboardResponse:
        now = datetime.now(self.tz)
        w = self.day_window(now.date())
        assignee = user_id if restrict else None

        today_follow_ups = len(
            await self.follow_ups.list_between(w.start, w.end, assigned_user_id=assignee)
        )
        overdue = len(await self.follow_ups.list_overdue(now, assigned_user_id=assignee))
        hot_leads = await self._count(
            select(func.count())
            .select_from(Lead)
            .where(Lead.business_id == self.business_id)
            .where(Lead.status == LeadStatus.HOT)
        )

        return DashboardResponse(
            greeting=_greeting(now),
            today=DashboardToday(
                follow_ups=today_follow_ups,
                new_leads=await self._new_leads(w),
                hot_leads=hot_leads,
                overdue=overdue,
            ),
            conversions=DashboardConversions(
                new_customers=await self._new_customers(w),
                converted_today=await self.leads.count_conversions(w.start, w.end),
            ),
            ai_activity=await self._ai_activity(limit=5),
            generated_at=now,
        )

    async def _ai_activity(self, limit: int = 5) -> list[AIActivityItem]:
        items: list[AIActivityItem] = []

        stmt = (
            select(FollowUp, Customer.name)
            .join(Customer, Customer.id == FollowUp.customer_id)
            .where(FollowUp.business_id == self.business_id)
            .where(FollowUp.created_by_ai.is_(True))
            .order_by(FollowUp.created_at.desc())
            .limit(limit)
        )
        for follow_up, name in (await self.session.execute(stmt)).all():
            items.append(
                AIActivityItem(
                    customer_id=follow_up.customer_id,
                    customer_name=name,
                    action="Follow-up created",
                    at=follow_up.created_at,
                )
            )

        stmt = (
            select(ConversationEvent, Customer.name)
            .join(Customer, Customer.id == ConversationEvent.customer_id)
            .where(ConversationEvent.business_id == self.business_id)
            .order_by(ConversationEvent.created_at.desc())
            .limit(limit)
        )
        for event, name in (await self.session.execute(stmt)).all():
            items.append(
                AIActivityItem(
                    customer_id=event.customer_id,
                    customer_name=name,
                    action=(
                        "AI note added" if event.source == "tell_ai" else "Recording processed"
                    ),
                    at=event.created_at,
                )
            )

        items.sort(key=lambda i: i.at, reverse=True)
        return items[:limit]

    # ---------------- daily ----------------
    async def daily(
        self, day: date | None = None, *, with_insights: bool = True
    ) -> DailyReportResponse:
        now = datetime.now(self.tz)
        day = day or now.date()
        w = self.day_window(day)

        report = DailyReportResponse(
            report_date=day,
            business_id=self.business_id,
            new_leads=await self._new_leads(w),
            customers_contacted=await self.events.distinct_customers_contacted(w.start, w.end),
            interested_leads=await self._customers_in_status(w, LeadStatus.INTERESTED),
            hot_leads=await self._customers_in_status(w, LeadStatus.HOT),
            converted_customers=await self.leads.count_conversions(w.start, w.end),
            follow_ups=await self._follow_up_metrics(w, now),
            queries=await self._query_metrics(w),
            important_follow_ups=await self._important_follow_ups(now),
        )
        if with_insights:
            report.ai_insights = await self._insights(report.model_dump(mode="json"))
        await self._persist(report, "daily", w)
        return report

    # ---------------- weekly / monthly ----------------
    async def period(
        self, period: str, anchor: date | None = None, *, with_insights: bool = True
    ) -> PeriodReportResponse:
        now = datetime.now(self.tz)
        anchor = anchor or now.date()
        w = self.week_window(anchor) if period == "weekly" else self.month_window(anchor)

        counts = await self.leads.counts_by_status(w.start, w.end)
        total_leads = sum(counts.values())
        converted = await self.leads.count_conversions(w.start, w.end)
        conversion_rate = round((converted / total_leads) * 100, 2) if total_leads else 0.0

        report = PeriodReportResponse(
            title="WEEKLY SALES REPORT" if period == "weekly" else "MONTHLY SALES REPORT",
            period=period,
            period_start=w.start_date,
            period_end=w.end_date,
            business_id=self.business_id,
            leads=LeadMetrics(
                new_leads=counts.get(LeadStatus.NEW, 0),
                contacted=await self._customers_in_status(w, LeadStatus.CONTACTED),
                interested=await self._customers_in_status(w, LeadStatus.INTERESTED),
                hot=await self._customers_in_status(w, LeadStatus.HOT),
                converted=converted,
                lost=await self._customers_in_status(w, LeadStatus.LOST),
                conversion_rate=conversion_rate,
            ),
            follow_ups=await self._follow_up_metrics(w, now),
            queries=await self._query_metrics(w),
            top_requirements=await self._top_values(Customer.requirement, w),
            common_questions=await self._top_query_categories(w),
            common_objections=await self._top_json_values("objections", w),
            pending_opportunities=await self._pending_opportunities(),
            important_follow_ups=await self._important_follow_ups(now, limit=8),
        )
        if with_insights:
            report.ai_insights = await self._insights(report.model_dump(mode="json"))
        await self._persist(report, period, w)
        return report

    async def _top_values(self, column, w: Window, limit: int = 5) -> list[dict]:  # noqa: ANN001
        stmt = (
            select(column, func.count().label("count"))
            .where(Customer.business_id == self.business_id)
            .where(Customer.updated_at >= w.start)
            .where(Customer.updated_at < w.end)
            .where(column.is_not(None))
            .group_by(column)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [
            {"value": value, "count": int(count)}
            for value, count in (await self.session.execute(stmt)).all()
        ]

    async def _top_query_categories(self, w: Window, limit: int = 5) -> list[dict]:
        counts = await self.reports.query_category_counts(w.start_date, w.end_date)
        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [{"category": category.value, "count": count} for category, count in ranked]

    async def _top_json_values(self, column_name: str, w: Window, limit: int = 5) -> list[dict]:
        """Objections/competitors live in a JSON array; aggregate in Python for portability."""
        stmt = (
            select(getattr(Customer, column_name))
            .where(Customer.business_id == self.business_id)
            .where(Customer.updated_at >= w.start)
            .where(Customer.updated_at < w.end)
            .where(getattr(Customer, column_name).is_not(None))
            .limit(2000)
        )
        tally: dict[str, int] = {}
        for (values,) in (await self.session.execute(stmt)).all():
            for value in values or []:
                key = str(value).strip().lower()
                if key:
                    tally[key] = tally.get(key, 0) + 1
        ranked = sorted(tally.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [{"value": value, "count": count} for value, count in ranked]

    async def _pending_opportunities(self, limit: int = 10) -> list[dict]:
        stmt = (
            select(Customer)
            .where(Customer.business_id == self.business_id)
            .where(
                Customer.lead_status.in_(
                    [LeadStatus.HOT, LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP]
                )
            )
            .order_by(Customer.lead_score.desc(), Customer.updated_at.desc())
            .limit(limit)
        )
        return [
            {
                "customer_id": str(c.id),
                "name": c.name,
                "requirement": c.requirement,
                "status": c.lead_status,
                "budget_max": float(c.budget_max) if c.budget_max is not None else None,
            }
            for c in (await self.session.execute(stmt)).scalars().all()
        ]

    # ---------------- insights ----------------
    async def _insights(self, metrics: dict) -> list[str]:
        """LLM phrasing over real numbers; deterministic fallback if AI is unavailable."""
        fallback = _fallback_insights(metrics)
        if self.llm is None:
            return fallback
        try:
            result = await self.llm.complete_json(
                system_prompt=INSIGHTS_SYSTEM_PROMPT,
                user_prompt=json.dumps(_insight_inputs(metrics), default=str)[:6000],
                max_output_tokens=600,
            )
            parsed = json.loads(result.content or "{}")
            insights = [str(i).strip() for i in parsed.get("insights", []) if str(i).strip()]
            return insights[:6] or fallback
        except Exception:  # noqa: BLE001 - a report must never fail because of the LLM
            log.info("insights_fallback_used")
            return fallback

    async def _persist(self, report, period: str, w: Window) -> None:  # noqa: ANN001
        metrics = report.model_dump(mode="json")
        await self.reports.upsert_snapshot(
            period=period,
            period_start=w.start_date,
            period_end=w.end_date,
            metrics=metrics,
            ai_insights=list(report.ai_insights),
            model_name=getattr(self.llm, "model", None),
        )
        if period == "daily":
            for key in ("new_leads", "customers_contacted", "converted_customers"):
                await self.reports.record_metric(w.start_date, key, float(metrics.get(key, 0)))

    # ---------------- housekeeping ----------------
    async def stale_jobs(self, older_than_minutes: int = 90) -> list[AIProcessingJob]:
        cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
        stmt = (
            select(AIProcessingJob)
            .where(AIProcessingJob.business_id == self.business_id)
            .where(
                AIProcessingJob.status.in_(
                    [
                        JobStatus.QUEUED, JobStatus.TRANSCRIBING,
                        JobStatus.ANALYZING, JobStatus.EXTRACTING,
                    ]
                )
            )
            .where(AIProcessingJob.created_at < cutoff)
        )
        return list((await self.session.execute(stmt)).scalars().all())


def _greeting(now: datetime) -> str:
    hour = now.hour
    if hour < 12:
        return "Good Morning 👋"
    if hour < 17:
        return "Good Afternoon 👋"
    return "Good Evening 👋"


def _insight_inputs(metrics: dict) -> dict:
    keep = (
        "report_date", "period", "period_start", "period_end", "new_leads",
        "customers_contacted", "interested_leads", "hot_leads",
        "converted_customers", "follow_ups", "queries", "leads",
    )
    return {k: v for k, v in metrics.items() if k in keep}


def _fallback_insights(metrics: dict) -> list[str]:
    """Pure arithmetic restatement - safe when the LLM is unavailable."""
    out: list[str] = []
    follow_ups = metrics.get("follow_ups") or {}
    queries = metrics.get("queries") or {}
    leads = metrics.get("leads") or {}

    interested = metrics.get("interested_leads", leads.get("interested", 0))
    converted = metrics.get("converted_customers", leads.get("converted", 0))
    if interested:
        out.append(f"{interested} customers showed interest in this period.")
    if queries.get("price_concerns"):
        out.append(f"{queries['price_concerns']} customers raised price concerns.")
    if queries.get("callbacks_requested"):
        out.append(f"{queries['callbacks_requested']} customers requested callbacks.")
    if converted:
        out.append(f"{converted} leads converted.")
    if follow_ups.get("overdue"):
        out.append(f"{follow_ups['overdue']} follow-ups are overdue.")
    if leads.get("conversion_rate"):
        out.append(f"Conversion rate for this period is {leads['conversion_rate']}%.")
    return out or ["No activity recorded for this period yet."]
