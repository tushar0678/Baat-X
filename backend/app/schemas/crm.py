from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.phone import mask_phone, normalize_phone
from app.models.enums import (
    ConversationSource,
    LeadStatus,
    PurchaseIntent,
    QueryCategory,
    Sentiment,
)


class CustomerBase(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    company: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=160)
    requirement: str | None = None
    product: str | None = Field(default=None, max_length=160)
    service: str | None = Field(default=None, max_length=160)
    quantity: str | None = Field(default=None, max_length=64)
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    timeline: str | None = Field(default=None, max_length=160)
    availability: str | None = Field(default=None, max_length=255)
    price_discussion: str | None = None
    purchase_intent: PurchaseIntent = PurchaseIntent.UNKNOWN
    sentiment: Sentiment = Sentiment.UNKNOWN
    pain_points: list[str] | None = None
    objections: list[str] | None = None
    competitors: list[str] | None = None
    decision_maker: str | None = Field(default=None, max_length=160)
    query: str | None = None
    topic: str | None = Field(default=None, max_length=255)
    summary: str | None = None

    @field_validator("budget_max")
    @classmethod
    def _check_budget(cls, v: Decimal | None, info):  # noqa: ANN001
        lo = info.data.get("budget_min")
        if v is not None and lo is not None and v < lo:
            raise ValueError("budget_max must be greater than or equal to budget_min")
        return v


class CustomerCreate(CustomerBase):
    lead_status: LeadStatus = LeadStatus.NEW
    source: ConversationSource = ConversationSource.MANUAL
    owner_user_id: uuid.UUID | None = None


class CustomerUpdate(CustomerBase):
    lead_status: LeadStatus | None = None
    lead_score: int | None = Field(default=None, ge=0, le=100)
    owner_user_id: uuid.UUID | None = None


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    normalized_phone: str | None
    phone_masked: str | None = None
    lead_status: LeadStatus
    lead_score: int
    source: ConversationSource
    owner_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    last_interaction_at: datetime | None
    next_follow_up_at: datetime | None


class CustomerListFilters(BaseModel):
    search: str | None = Field(default=None, max_length=120)
    lead_status: LeadStatus | None = None
    purchase_intent: PurchaseIntent | None = None
    min_budget: Decimal | None = Field(default=None, ge=0)
    max_budget: Decimal | None = Field(default=None, ge=0)
    location: str | None = None
    owner_user_id: uuid.UUID | None = None
    has_pending_follow_up: bool | None = None
    updated_after: datetime | None = None

    @field_validator("search")
    @classmethod
    def _normalize(cls, v: str | None) -> str | None:
        return v.strip() if v else None


class TimelineEntry(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    kind: str  # conversation | follow_up_created | follow_up_completed | status_change
    title: str
    summary: str | None = None
    highlights: dict | None = None
    source: ConversationSource | None = None
    primary_query_category: QueryCategory | None = None


class CustomerTimelineResponse(BaseModel):
    customer_id: uuid.UUID
    name: str | None
    phone_masked: str | None
    entries: list[TimelineEntry]


class DuplicateCandidate(BaseModel):
    customer_id: uuid.UUID
    name: str | None
    phone_masked: str | None
    last_interaction_at: datetime | None
    match_reason: str


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str | None = None
    customer_phone_masked: str | None = None
    status: LeadStatus
    score: int
    source: ConversationSource
    assigned_user_id: uuid.UUID | None
    converted_at: datetime | None
    lost_reason: str | None
    created_at: datetime
    updated_at: datetime


class LeadStatusUpdate(BaseModel):
    status: LeadStatus
    reason: str | None = Field(default=None, max_length=255)


class LeadConvertRequest(BaseModel):
    value_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    note: str | None = Field(default=None, max_length=1000)


class LeadFunnelResponse(BaseModel):
    total_leads: int
    by_status: dict[LeadStatus, int]
    converted_leads: int
    conversion_rate: float
    converted_today: int
    converted_this_week: int
    converted_this_month: int


def masked(phone: str | None) -> str | None:
    return mask_phone(phone) or None


def normalized(phone: str | None, region: str = "IN") -> str | None:
    return normalize_phone(phone, region)
