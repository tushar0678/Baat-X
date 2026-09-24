from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import WhatsAppMessageStatus


class WhatsAppDraftRequest(BaseModel):
    customer_id: uuid.UUID
    purpose: str = Field(
        default="follow_up_summary", max_length=64,
        description="follow_up_summary | quotation | thank_you | meeting_confirmation",
    )
    extra_instruction: str | None = Field(default=None, max_length=500)


class WhatsAppDraftResponse(BaseModel):
    message_id: uuid.UUID
    customer_id: uuid.UUID
    to_phone_masked: str
    body: str
    status: WhatsAppMessageStatus
    disclaimer: str = (
        "Review before sending. BaatX never sends a customer message without your approval."
    )


class WhatsAppSendRequest(BaseModel):
    message_id: uuid.UUID
    approved: bool = Field(description="Must be true - explicit human approval is mandatory.")
    edited_body: str | None = Field(default=None, max_length=4000)


class WhatsAppSendResponse(BaseModel):
    message_id: uuid.UUID
    status: WhatsAppMessageStatus
    sent_at: datetime | None
    provider_message_id: str | None
