from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.deps import CurrentUser, DbDep, requires
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
    scope = principal.scope()
    return await _service(db, principal).dashboard(user_ids=scope.user_ids)


@router.get("/reports/daily", response_model=DailyReportResponse)
async def daily_report(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("report:read")],
    report_date: Annotated[date | None, Query(alias="date")] = None,
    insights: Annotated[bool, Query()] = True,
) -> DailyReportResponse:
    """A salesperson's daily report covers their own day, not the whole business.

    Reports were previously unscoped entirely: every count, every "top
    requirement" and every named follow-up came from the full organization.
    That made this endpoint a complete read of the CRM for anyone who could
    call it - including the customer names in ``important_follow_ups``.
    """
    scope = principal.scope()
    return await _service(db, principal).daily(
        report_date, with_insights=insights, user_ids=scope.user_ids
    )


@router.get("/reports/weekly", response_model=PeriodReportResponse)
async def weekly_report(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("report:read")],
    anchor: Annotated[date | None, Query()] = None,
    insights: Annotated[bool, Query()] = True,
) -> PeriodReportResponse:
    scope = principal.scope()
    return await _service(db, principal).period(
        "weekly", anchor, with_insights=insights, user_ids=scope.user_ids
    )


@router.get("/reports/monthly", response_model=PeriodReportResponse)
async def monthly_report(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("report:read")],
    anchor: Annotated[date | None, Query()] = None,
    insights: Annotated[bool, Query()] = True,
) -> PeriodReportResponse:
    scope = principal.scope()
    return await _service(db, principal).period(
        "monthly", anchor, with_insights=insights, user_ids=scope.user_ids
    )