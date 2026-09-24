from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FollowUpStatus, FollowUpType, NotificationType


class FollowUpCreate(BaseModel):
    customer_id: uuid.UUID
    type: FollowUpType = FollowUpType.GENERAL_FOLLOW_UP
    title: str = Field(min_length=2, max_length=200)
    due_at: datetime
    due_time_known: bool = True
    reason: str | None = Field(default=None, max_length=2000)
    notes: str | None = None
    assigned_user_id: uuid.UUID | None = None
    customer_requested_callback: bool = False


class FollowUpUpdate(BaseModel):
    status: FollowUpStatus | None = None
    due_at: datetime | None = None
    type: FollowUpType | None = None
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    assigned_user_id: uuid.UUID | None = None


class FollowUpResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str | None = None
    customer_phone_masked: str | None = None
    type: FollowUpType
    status: FollowUpStatus
    title: str
    reason: str | None
    notes: str | None
    due_at: datetime
    due_time_known: bool
    assigned_user_id: uuid.UUID | None
    created_by_ai: bool
    confidence: float | None
    completed_at: datetime | None
    customer_requested_callback: bool
    is_overdue: bool = False


class FollowUpBoard(BaseModel):
    """Exactly the sections rendered on the Follow-ups screen."""

    today: list[FollowUpResponse]
    tomorrow: list[FollowUpResponse]
    upcoming: list[FollowUpResponse]
    overdue: list[FollowUpResponse]
    completed: list[FollowUpResponse]
    counts: dict[str, int]


class SmartSuggestion(BaseModel):
    kind: str
    customer_id: uuid.UUID
    customer_name: str | None
    message: str
    suggested_type: FollowUpType
    suggested_due_at: datetime
    is_ai_generated: bool = True


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    customer_id: uuid.UUID | None
    follow_up_id: uuid.UUID | None
    created_at: datetime
    read_at: datetime | None
