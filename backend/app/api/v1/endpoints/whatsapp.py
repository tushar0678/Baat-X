from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Request, status

from app.auth.deps import CurrentUser, DbDep, requires
from app.auth.rbac import scope_filter
from app.core.errors import NotFoundError
from app.repositories.audit_repo import AuditRepository
from app.repositories.customer_repo import CustomerRepository
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
    """Creates a draft only. Nothing is sent until the user explicitly approves.

    The draft is generated from the customer's CRM history, so drafting against
    a customer you cannot open would hand you their requirement, budget and
    conversation summary through the message body.
    """
    scope = scope_filter(principal.role, principal.user_id)
    customer = await CustomerRepository(db, principal.business_id).get_or_404(payload.customer_id)

    if not scope.allows(customer):
        raise NotFoundError(
            "customer not found", user_message="We couldn't find that customer."
        )

    return await _service(db, principal).draft(payload, actor_id=principal.user_id)


@router.post("/send", response_model=WhatsAppSendResponse)
async def send(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("whatsapp:send")],
    payload: WhatsAppSendRequest,
) -> WhatsAppSendResponse:
    """Requires ``approved = true``; the API refuses to send otherwise."""
    scope = scope_filter(principal.role, principal.user_id)
    service = _service(db, principal)

    message = await service.get_message_or_404(payload.message_id)
    customer = await CustomerRepository(db, principal.business_id).get_or_404(message.customer_id)

    # Sending is irreversible and goes to a real person. The ownership check
    # matters more here than anywhere else in the API.
    if not scope.allows(customer):
        raise NotFoundError("message not found", user_message="We couldn't find that message.")

    result = await service.send(payload, actor_id=principal.user_id)

    await AuditRepository(db, principal.business_id).record(
        action="whatsapp.sent",
        actor_user_id=principal.user_id,
        entity_type="whatsapp_message",
        entity_id=result.message_id,
        request_id=getattr(request.state, "request_id", None),
        # Never the body or the number - this row is kept long after the
        # message is, and it is read by people who weren't on the thread.
        metadata={"customer_id": str(customer.id), "edited": payload.edited_body is not None},
    )
    return result


@router.post("/{message_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
async def discard(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("whatsapp:draft")],
    message_id: uuid.UUID,
) -> None:
    scope = scope_filter(principal.role, principal.user_id)
    service = _service(db, principal)

    message = await service.get_message_or_404(message_id)
    customer = await CustomerRepository(db, principal.business_id).get_or_404(message.customer_id)

    if not scope.allows(customer):
        raise NotFoundError("message not found", user_message="We couldn't find that message.")

    await service.discard(message_id)
