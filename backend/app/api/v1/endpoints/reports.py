from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.deps import CurrentUser, DbDep, requires
from app.auth.rbac import can_read_all
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
    return await _service(db, principal).dashboard(
        user_id=principal.user_id, restrict=not can_read_all(principal.role)
    )


@router.get("/reports/daily", response_model=DailyReportResponse)
async def daily_report(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("report:read")],
    report_date: Annotated[date | None, Query(alias="date")] = None,
    insights: Annotated[bool, Query()] = True,
) -> DailyReportResponse:
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
