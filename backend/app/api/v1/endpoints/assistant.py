from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Request

from app.auth.deps import CurrentUser, DbDep, requires
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
    """Answers only from data the caller could already open in the app.

    The assistant is handed the caller's own scope - not a wider one - because
    asking is otherwise a way around the screens. A manager gets
    organization-wide answers, a team lead their team's, a salesperson their
    own, and the same rules govern the actions it can take.
    """
    service = AssistantService(
        db,
        principal.business_id,
        llm=llm_provider(),
        scope=principal.scope(),
        timezone=principal.business.timezone,
    )

    response = await service.handle(payload)

    if response.kind == "action_executed":
        await AuditRepository(db, principal.business_id).record(
            action="assistant.action_executed",
            actor_user_id=principal.user_id,
            request_id=getattr(request.state, "request_id", None),
            # Ids and scope only - never the query text, which routinely
            # contains customer names and numbers.
            metadata={
                "affected": [str(i) for i in response.affected_ids],
                "scope": str(principal.scope().scope),
            },
        )
        await db.commit()

    return response
