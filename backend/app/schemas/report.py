from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import QueryCategory


class DashboardToday(BaseModel):
    follow_ups: int
    new_leads: int
    hot_leads: int
    overdue: int


class DashboardConversions(BaseModel):
    new_customers: int
    converted_today: int


class AIActivityItem(BaseModel):
    customer_id: uuid.UUID | None
    customer_name: str | None
    action: str
    at: datetime


class DashboardResponse(BaseModel):
    greeting: str
    prompt: str = "What happened with your customer?"
    today: DashboardToday
    conversions: DashboardConversions
    ai_activity: list[AIActivityItem]
    generated_at: datetime


class FollowUpMetrics(BaseModel):
    created: int
    completed: int
    pending: int
    overdue: int


class LeadMetrics(BaseModel):
    new_leads: int
    contacted: int
    interested: int
    hot: int
    converted: int
    lost: int
    conversion_rate: float


class QueryMetrics(BaseModel):
    total_queries: int
    by_category: dict[QueryCategory, int]
    quotations_requested: int
    price_concerns: int
    callbacks_requested: int
    availability_queries: int


class ImportantFollowUp(BaseModel):
    customer_id: uuid.UUID
    customer_name: str | None
    action: str
    due_at: datetime


class DailyReportResponse(BaseModel):
    title: str = "DAILY SALES REPORT"
    report_date: date
    business_id: uuid.UUID
    new_leads: int
    customers_contacted: int
    interested_leads: int
    hot_leads: int
    converted_customers: int
    follow_ups: FollowUpMetrics
    queries: QueryMetrics
    important_follow_ups: list[ImportantFollowUp]
    ai_insights: list[str] = Field(default_factory=list)
    insights_are_ai_generated: bool = True
    metrics_source: str = "database"


class PeriodReportResponse(BaseModel):
    title: str
    period: str
    period_start: date
    period_end: date
    business_id: uuid.UUID
    leads: LeadMetrics
    follow_ups: FollowUpMetrics
    queries: QueryMetrics
    top_requirements: list[dict]
    common_questions: list[dict]
    common_objections: list[dict]
    pending_opportunities: list[dict]
    important_follow_ups: list[ImportantFollowUp]
    ai_insights: list[str] = Field(default_factory=list)
    insights_are_ai_generated: bool = True
    metrics_source: str = "database"
