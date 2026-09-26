from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.auth.deps import CurrentUser, DbDep, requires
from app.auth.rbac import scope_filter
from app.core.errors import NotFoundError
from app.repositories.audit_repo import AuditRepository
from app.repositories.customer_repo import CustomerRepository
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


def _not_found() -> NotFoundError:
    return NotFoundError("follow-up not found", user_message="We couldn't find that follow-up.")


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
    """``FollowUpService.board`` only supports narrowing to a single owner
    (``assigned_user_id``), not an arbitrary set - so an unrestricted scope
    (owner/manager) passes ``None`` and sees everyone's board, while anyone
    else is restricted to their own. ``mine_only`` can narrow further but
    never widen: a manager asking for "mine" still only sees their own.
    """
    scope = scope_filter(principal.role, principal.user_id)
    if mine_only:
        assigned_user_id = principal.user_id
    else:
        assigned_user_id = None if scope.unrestricted else principal.user_id
    return await _service(db, principal).board(assigned_user_id=assigned_user_id)


@router.post("/follow-ups", response_model=FollowUpResponse, status_code=status.HTTP_201_CREATED)
async def create_follow_up(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("followup:write")],
    payload: FollowUpCreate,
) -> FollowUpResponse:
    scope = scope_filter(principal.role, principal.user_id)

    # A follow-up names a customer. Creating one against a customer you can't
    # open would confirm they exist and let you attach yourself to them.
    customer = await CustomerRepository(db, principal.business_id).get_or_404(payload.customer_id)
    if not scope.allows(customer):
        raise NotFoundError("customer not found", user_message="We couldn't find that customer.")

    # Assigning work to someone else is a separate privilege from creating it.
    if payload.assigned_user_id and payload.assigned_user_id != principal.user_id:
        principal.require("followup:assign")

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
    scope = scope_filter(principal.role, principal.user_id)
    service = _service(db, principal)

    existing = await service.repo.get_or_404(follow_up_id)

    # Previously any member could complete, reschedule or cancel a colleague's
    # follow-up - silently losing them the reminder.
    if not scope.allows(existing):
        raise _not_found()

    if payload.assigned_user_id and payload.assigned_user_id != existing.assigned_user_id:
        principal.require("followup:assign")

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
    """``FollowUpService.smart_suggestions`` takes no scoping parameter at all
    in the current implementation - it surfaces organization-wide gaps
    (customer names included) to anyone holding ``followup:read``. Gated
    behind that permission for now; row-level scoping would need to be added
    inside ``smart_suggestions`` itself (its three internal queries), not
    just here.
    """
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
    """Marking read returns the notification body, so the recipient check is
    a read-authorization check, not just a tidiness one."""
    service = NotificationService(db, principal.business_id)
    notification = await service.get_or_404(notification_id)

    if notification.user_id != principal.user_id:
        raise NotFoundError(
            "notification not found", user_message="We couldn't find that notification."
        )

    return NotificationResponse.model_validate(await service.mark_read(notification_id))
