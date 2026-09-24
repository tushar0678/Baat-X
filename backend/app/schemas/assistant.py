from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class AssistantQueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    confirm_token: str | None = Field(
        default=None,
        description="Echo back the token from a pending confirmation to execute the action.",
    )


class AssistantAction(BaseModel):
    intent: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    destructive: bool = False


class AssistantQueryResponse(BaseModel):
    answer: str
    kind: Literal["answer", "confirmation_required", "action_executed", "unsupported"] = "answer"
    data: list[dict[str, Any]] = Field(default_factory=list)
    action: AssistantAction | None = None
    confirm_token: str | None = None
    affected_ids: list[uuid.UUID] = Field(default_factory=list)
    is_ai_generated: bool = True
