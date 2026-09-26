from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.deps import CurrentUser, DbDep, requires
from app.auth.rbac import VisibilityScope
from app.schemas.report import DailyReportResponse, DashboardResponse, PeriodReportResponse
from app.services.ai.factory import llm_provider
from app.services.reports.report_service import ReportService

router = APIRouter(tags=["Reports"])


def _service(db, principal: CurrentUser) -> ReportService:  # noqa: ANN001
    return ReportService(
        db, principal.business_id, timezone=principal.business.timezone, llm=llm_provider()
    )


@router.get("/dashboard", response_model=DashboardResponse, summary="Home dashboard")
async def dashboard(
    db: DbDep, principal: Annotated[CurrentUser, requires("report:read")]
) -> DashboardResponse:
    """A salesperson's dashboard covers their own day; a manager's covers
    everyone's. ``ReportService.dashboard`` takes ``restrict`` + a single
    ``user_id`` (not a set) because it only ever narrows to "me" - team-wide
    scoping for a team lead isn't implemented at the service layer yet, so a
    team lead currently sees their own numbers, same as a member. That's the
    safe direction to under-scope in, not a data leak.
    """
    scope = principal.scope()
    restrict = scope.scope is not VisibilityScope.ORG
    return await _service(db, principal).dashboard(
        user_id=principal.user_id, restrict=restrict
    )


@router.get("/reports/daily", response_model=DailyReportResponse)
async def daily_report(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("report:read")],
    report_date: Annotated[date | None, Query(alias="date")] = None,
    insights: Annotated[bool, Query()] = True,
) -> DailyReportResponse:
    """Daily/weekly/monthly reports are business-wide in the current service
    implementation - they were never scoped even before the multi-org change,
    and adding per-owner filtering here requires editing every private
    aggregation method in ReportService (``_new_leads``, ``_new_customers``,
    ``_important_follow_ups``, ``_top_values``, etc.), not just this endpoint.
    Gated behind ``report:read`` for now; only owners/managers should hold
    that permission until row-level scoping is added to these reports.
    """
    return await _service(db, principal).daily(report_date, with_insights=insights)


@router.get("/reports/weekly", response_model=PeriodReportResponse)
async def weekly_report(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("report:read")],
    anchor: Annotated[date | None, Query()] = None,
    insights: Annotated[bool, Query()] = True,
) -> PeriodReportResponse:
    return await _service(db, principal).period("weekly", anchor, with_insights=insights)


@router.get("/reports/monthly", response_model=PeriodReportResponse)
async def monthly_report(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("report:read")],
    anchor: Annotated[date | None, Query()] = None,
    insights: Annotated[bool, Query()] = True,
) -> PeriodReportResponse:
    return await _service(db, principal).period("monthly", anchor, with_insights=insights)