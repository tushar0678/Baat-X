from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.auth.deps import CurrentUser, DbDep, requires
from app.auth.rbac import can_read_all
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


@router.get("", response_model=Page[CustomerResponse], summary="List and search customers")
async def list_customers(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:read")],
    filters: Annotated[CustomerListFilters, Depends()],
    params: Annotated[PageParams, Depends()],
) -> Page[CustomerResponse]:
    restrict = None if can_read_all(principal.role) else principal.user_id
    return await _service(db, principal).list_customers(
        filters, params, restrict_to_user_id=restrict
    )


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:write")],
    payload: CustomerCreate,
) -> CustomerResponse:
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
    service = _service(db, principal)
    customer = await service.customers.get_or_404(customer_id)
    if not can_read_all(principal.role) and customer.owner_user_id != principal.user_id:
        principal.require("customer:read_all")  # raises 403 for salespeople
    return CustomerService.to_response(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:write")],
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
) -> CustomerResponse:
    customer = await _service(db, principal).update(
        customer_id, payload, actor_id=principal.user_id
    )
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
    return await _service(db, principal).timeline(customer_id, limit=limit)
