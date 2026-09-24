from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.auth.deps import CurrentUser, DbDep, requires
from app.auth.rbac import can_read_all
from app.repositories.audit_repo import AuditRepository
from app.schemas.followup import (
    FollowUpBoard,
    FollowUpCreate,
    FollowUpResponse,
    FollowUpUpdate,
    NotificationResponse,
    SmartSuggestion,
)
from app.services.notifications.service import NotificationService
from app.services.reminders.followup_service import FollowUpService

router = APIRouter(tags=["Follow-ups"])


def _service(db, principal: CurrentUser) -> FollowUpService:  # noqa: ANN001
    return FollowUpService(db, principal.business_id, principal.business.timezone)


@router.get(
    "/follow-ups",
    response_model=FollowUpBoard,
    summary="Today / Tomorrow / Upcoming / Overdue / Completed",
)
async def board(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("followup:read")],
    mine_only: Annotated[bool, Query()] = False,
) -> FollowUpBoard:
    restrict = principal.user_id if (mine_only or not can_read_all(principal.role)) else None
    return await _service(db, principal).board(assigned_user_id=restrict)


@router.post("/follow-ups", response_model=FollowUpResponse, status_code=status.HTTP_201_CREATED)
async def create_follow_up(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("followup:write")],
    payload: FollowUpCreate,
) -> FollowUpResponse:
    service = _service(db, principal)
    follow_up = await service.create(payload, actor_id=principal.user_id)
    await AuditRepository(db, principal.business_id).record(
        action="followup.created",
        actor_user_id=principal.user_id,
        entity_type="follow_up",
        entity_id=follow_up.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return await service.to_response(follow_up)


@router.patch("/follow-ups/{follow_up_id}", response_model=FollowUpResponse)
async def update_follow_up(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("followup:write")],
    follow_up_id: uuid.UUID,
    payload: FollowUpUpdate,
) -> FollowUpResponse:
    service = _service(db, principal)
    follow_up = await service.update(follow_up_id, payload, actor_id=principal.user_id)
    await AuditRepository(db, principal.business_id).record(
        action="followup.updated",
        actor_user_id=principal.user_id,
        entity_type="follow_up",
        entity_id=follow_up.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"fields": sorted(payload.model_dump(exclude_unset=True).keys())},
    )
    return await service.to_response(follow_up)


@router.get(
    "/follow-ups/suggestions",
    response_model=list[SmartSuggestion],
    summary="Smart follow-up intelligence (suggestions only - never auto-contacts)",
)
async def suggestions(
    db: DbDep, principal: Annotated[CurrentUser, requires("followup:read")]
) -> list[SmartSuggestion]:
    return await _service(db, principal).smart_suggestions()


@router.get("/notifications", response_model=list[NotificationResponse], tags=["Notifications"])
async def notifications(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("followup:read")],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[NotificationResponse]:
    rows = await NotificationService(db, principal.business_id).list_for_user(
        principal.user_id, limit
    )
    return [NotificationResponse.model_validate(row) for row in rows]


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    tags=["Notifications"],
)
async def mark_read(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("followup:read")],
    notification_id: uuid.UUID,
) -> NotificationResponse:
    service = NotificationService(db, principal.business_id)
    return NotificationResponse.model_validate(await service.mark_read(notification_id))
