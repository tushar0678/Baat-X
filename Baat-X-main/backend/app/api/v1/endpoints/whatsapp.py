from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Request, status

from app.auth.deps import CurrentUser, DbDep, requires
from app.repositories.audit_repo import AuditRepository
from app.schemas.whatsapp import (
    WhatsAppDraftRequest,
    WhatsAppDraftResponse,
    WhatsAppSendRequest,
    WhatsAppSendResponse,
)
from app.services.ai.factory import llm_provider
from app.services.whatsapp.service import WhatsAppService

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


def _service(db, principal: CurrentUser) -> WhatsAppService:  # noqa: ANN001
    return WhatsAppService(db, principal.business_id, llm=llm_provider())


@router.post("/draft", response_model=WhatsAppDraftResponse, status_code=status.HTTP_201_CREATED)
async def draft(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("whatsapp:draft")],
    payload: WhatsAppDraftRequest,
) -> WhatsAppDraftResponse:
    """Creates a draft only. Nothing is sent until the user explicitly approves."""
    return await _service(db, principal).draft(payload, actor_id=principal.user_id)


@router.post("/send", response_model=WhatsAppSendResponse)
async def send(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("whatsapp:send")],
    payload: WhatsAppSendRequest,
) -> WhatsAppSendResponse:
    """Requires `approved = true`; the API refuses to send otherwise."""
    result = await _service(db, principal).send(payload, actor_id=principal.user_id)
    await AuditRepository(db, principal.business_id).record(
        action="whatsapp.sent",
        actor_user_id=principal.user_id,
        entity_type="whatsapp_message",
        entity_id=result.message_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return result


@router.post("/{message_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
async def discard(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("whatsapp:draft")],
    message_id: uuid.UUID,
) -> None:
    await _service(db, principal).discard(message_id)
