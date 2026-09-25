from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.auth.deps import CurrentUser, DbDep, requires
from app.auth.rbac import scope_filter
from app.core.errors import NotFoundError
from app.core.pagination import Page, PageParams
from app.repositories.audit_repo import AuditRepository
from app.schemas.crm import (
    CustomerCreate,
    CustomerListFilters,
    CustomerResponse,
    CustomerTimelineResponse,
    CustomerUpdate,
)
from app.services.crm.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["Customers"])


def _service(db, principal: CurrentUser) -> CustomerService:  # noqa: ANN001
    return CustomerService(db, principal.business_id, principal.business.country_code)


def _not_found() -> NotFoundError:
    """Same error whether the customer doesn't exist or isn't yours.

    The old code raised 403 here, which confirmed the record existed under
    another owner - enough to enumerate a colleague's book by id.
    """
    return NotFoundError("customer not found", user_message="We couldn't find that customer.")


@router.get("", response_model=Page[CustomerResponse], summary="List and search customers")
async def list_customers(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:read")],
    filters: Annotated[CustomerListFilters, Depends()],
    params: Annotated[PageParams, Depends()],
) -> Page[CustomerResponse]:
    """Search runs inside the caller's scope.

    ``filters.owner_user_id`` narrows the result but cannot widen it - asking
    for a colleague's id returns an empty page rather than their customers.
    """
    scope = scope_filter(principal.role, principal.user_id)
    return await _service(db, principal).list_customers(
        filters, params, restrict_to_user_ids=scope.user_ids
    )


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:write")],
    payload: CustomerCreate,
) -> CustomerResponse:
    # Handing a new customer to someone else is an assignment, not a create.
    if payload.owner_user_id and payload.owner_user_id != principal.user_id:
        principal.require("customer:assign")

    customer = await _service(db, principal).create(payload, actor_id=principal.user_id)

    await AuditRepository(db, principal.business_id).record(
        action="customer.created",
        actor_user_id=principal.user_id,
        entity_type="customer",
        entity_id=customer.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return CustomerService.to_response(customer)


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:read")],
    customer_id: uuid.UUID,
) -> CustomerResponse:
    scope = scope_filter(principal.role, principal.user_id)
    customer = await _service(db, principal).customers.get_or_404(customer_id)

    if not scope.allows(customer):
        raise _not_found()

    return CustomerService.to_response(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:write")],
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
) -> CustomerResponse:
    scope = scope_filter(principal.role, principal.user_id)
    service = _service(db, principal)

    existing = await service.customers.get_or_404(customer_id)
    if not scope.allows(existing):
        raise _not_found()

    # Reassignment is a distinct privilege from editing: a member may correct
    # their own customer's details without being able to move them away.
    if payload.owner_user_id and payload.owner_user_id != existing.owner_user_id:
        principal.require("customer:assign")

    customer = await service.update(customer_id, payload, actor_id=principal.user_id)

    await AuditRepository(db, principal.business_id).record(
        action="customer.updated",
        actor_user_id=principal.user_id,
        entity_type="customer",
        entity_id=customer.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"fields": sorted(payload.model_dump(exclude_unset=True).keys())},
    )
    return CustomerService.to_response(customer)


@router.get(
    "/{customer_id}/timeline",
    response_model=CustomerTimelineResponse,
    summary="Structured conversation history (never audio)",
)
async def customer_timeline(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:read")],
    customer_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CustomerTimelineResponse:
    """The timeline is the richest view in the CRM - summaries, budgets,
    objections. It was previously reachable by id with no ownership check."""
    scope = scope_filter(principal.role, principal.user_id)
    service = _service(db, principal)

    customer = await service.customers.get_or_404(customer_id)
    if not scope.allows(customer):
        raise _not_found()

    return await service.timeline(customer_id, limit=limit)
