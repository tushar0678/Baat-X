"""Schemas for AI extraction - the contract between the LLM, the API and Android.

Every extracted field is wrapped in a confidence envelope so the client can show
what the AI was sure about and the CRM merge policy can refuse to overwrite
higher-confidence data with a guess.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    ConversationSource,
    FollowUpType,
    JobStatus,
    LeadStatus,
    PurchaseIntent,
    QueryCategory,
    Sentiment,
)

T = TypeVar("T")

HIGH = "high"
MEDIUM = "medium"
LOW = "low"


def confidence_band(value: float) -> str:
    if value >= 0.90:
        return HIGH
    if value >= 0.60:
        return MEDIUM
    return LOW


class Field_(BaseModel, Generic[T]):
    """`{"value": ..., "confidence": 0.98, "source_text": "..."}`."""

    model_config = ConfigDict(populate_by_name=True)

    value: T | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    source_text: str | None = None

    @property
    def band(self) -> str:
        return confidence_band(self.confidence)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


class FollowUpExtraction(BaseModel):
    required: bool = False
    date: str | None = None          # raw expression, e.g. "Friday", "2 din baad"
    time: str | None = None
    type: FollowUpType = FollowUpType.GENERAL_FOLLOW_UP
    action: str | None = None
    reason: str | None = None
    customer_requested_callback: bool = False
    confidence: float = Field(0.0, ge=0.0, le=1.0)

    # Filled server-side by the time resolver; the LLM never sets these.
    resolved_due_at: datetime | None = None
    resolved_time_known: bool = False
    needs_confirmation: bool = False
    resolution_reason: str | None = None


class ExtractionPayload(BaseModel):
    """Normalised AI output. Anything unknown stays `None` - never invented."""

    model_config = ConfigDict(extra="ignore")

    # Customer
    customer_name: Field_[str] = Field(default_factory=Field_)
    phone_number: Field_[str] = Field(default_factory=Field_)
    email: Field_[str] = Field(default_factory=Field_)
    company: Field_[str] = Field(default_factory=Field_)
    location: Field_[str] = Field(default_factory=Field_)

    # Requirement
    requirement: Field_[str] = Field(default_factory=Field_)
    product: Field_[str] = Field(default_factory=Field_)
    service: Field_[str] = Field(default_factory=Field_)
    quantity: Field_[str] = Field(default_factory=Field_)
    budget: Field_[str] = Field(default_factory=Field_)
    budget_min: Field_[float] = Field(default_factory=Field_)
    budget_max: Field_[float] = Field(default_factory=Field_)
    currency: Field_[str] = Field(default_factory=Field_)
    price_discussed: Field_[str] = Field(default_factory=Field_)
    availability: Field_[str] = Field(default_factory=Field_)
    timeline: Field_[str] = Field(default_factory=Field_)

    # Sales
    purchase_intent: Field_[PurchaseIntent] = Field(default_factory=Field_)
    lead_status: Field_[LeadStatus] = Field(default_factory=Field_)
    lead_score: Field_[int] = Field(default_factory=Field_)
    sentiment: Field_[Sentiment] = Field(default_factory=Field_)
    pain_points: Field_[list[str]] = Field(default_factory=Field_)
    objections: Field_[list[str]] = Field(default_factory=Field_)
    competitors: Field_[list[str]] = Field(default_factory=Field_)
    decision_maker: Field_[str] = Field(default_factory=Field_)

    # Conversation
    customer_query: Field_[str] = Field(default_factory=Field_)
    query_categories: Field_[list[QueryCategory]] = Field(default_factory=Field_)
    topic: Field_[str] = Field(default_factory=Field_)
    important_points: Field_[list[str]] = Field(default_factory=Field_)
    summary: str | None = None

    follow_up: FollowUpExtraction = Field(default_factory=FollowUpExtraction)
    language_detected: str | None = None

    def non_null_fields(self) -> dict[str, Field_]:
        out: dict[str, Field_] = {}
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, Field_) and value.value not in (None, "", []):
                out[name] = value
        return out

    def overall_confidence(self) -> float:
        fields = self.non_null_fields()
        if not fields:
            return 0.0
        return round(sum(f.confidence for f in fields.values()) / len(fields), 4)


class TellAIRequest(BaseModel):
    text: str = Field(min_length=2, max_length=20_000)
    idempotency_key: str = Field(min_length=8, max_length=80)
    customer_id: uuid.UUID | None = None
    phone_hint: str | None = Field(default=None, max_length=32)
    source: ConversationSource = ConversationSource.TELL_AI
    client_recorded_at: datetime | None = None  # set by offline queue on Android


class ProcessAudioResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    stage_label: str
    progress: int


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    stage_label: str
    progress: int
    error_code: str | None = None
    error_message: str | None = None
    extraction_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None


class ReviewItem(BaseModel):
    """One line on the 'Here's what I understood' screen."""

    key: str
    label: str
    value: Any | None
    confidence: float
    band: str
    needs_confirmation: bool = False
    source_text: str | None = None


class ExtractionReviewResponse(BaseModel):
    extraction_id: uuid.UUID
    job_id: uuid.UUID
    customer_id: uuid.UUID | None
    matched_existing_customer: bool
    title: str = "Here's what I understood"
    items: list[ReviewItem]
    summary: str | None
    follow_up: FollowUpExtraction
    overall_confidence: float
    needs_confirmation: list[str] = Field(default_factory=list)
    payload: ExtractionPayload


class ApplyExtractionRequest(BaseModel):
    """User-reviewed corrections. Anything edited is treated as confidence 1.0."""

    customer_id: uuid.UUID | None = None
    create_customer: bool = True
    phone_override: str | None = None
    edited_fields: dict[str, Any] = Field(default_factory=dict)
    confirm_follow_up: bool = True
    follow_up_due_at: datetime | None = None
    follow_up_type: FollowUpType | None = None
    discard: bool = False


class ApplyExtractionResponse(BaseModel):
    customer_id: uuid.UUID
    conversation_event_id: uuid.UUID
    follow_up_id: uuid.UUID | None
    lead_status: LeadStatus
    updated_fields: list[str]
    skipped_low_confidence_fields: list[str]
