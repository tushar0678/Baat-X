from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Request

from app.auth.deps import CurrentUser, DbDep, requires
from app.auth.rbac import can_read_all
from app.repositories.audit_repo import AuditRepository
from app.schemas.assistant import AssistantQueryRequest, AssistantQueryResponse
from app.services.ai.factory import llm_provider
from app.services.assistant.service import AssistantService

router = APIRouter(prefix="/assistant", tags=["Assistant"])


@router.post("/query", response_model=AssistantQueryResponse, summary="Ask BaatX about your CRM")
async def query(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("assistant:query")],
    payload: AssistantQueryRequest,
) -> AssistantQueryResponse:
    service = AssistantService(
        db,
        principal.business_id,
        llm=llm_provider(),
        timezone=principal.business.timezone,
        user_id=principal.user_id,
        restrict_to_user=not can_read_all(principal.role),
    )
    response = await service.handle(payload)
    if response.kind == "action_executed":
        await AuditRepository(db, principal.business_id).record(
            action="assistant.action_executed",
            actor_user_id=principal.user_id,
            request_id=getattr(request.state, "request_id", None),
            metadata={"affected": [str(i) for i in response.affected_ids]},
        )
    return response
