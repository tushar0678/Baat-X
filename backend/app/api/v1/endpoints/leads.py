from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.auth.deps import CurrentUser, DbDep, requires
from app.auth.rbac import scope_filter
from app.core.errors import NotFoundError
from app.core.pagination import Page, PageParams
from app.core.phone import mask_phone
from app.models.crm import ConversionEvent
from app.models.enums import LeadStatus
from app.repositories.audit_repo import AuditRepository
from app.repositories.lead_repo import LeadRepository
from app.schemas.crm import (
    LeadConvertRequest,
    LeadFunnelResponse,
    LeadResponse,
    LeadStatusUpdate,
)
from app.services.crm.customer_service import CustomerService

router = APIRouter(prefix="/leads", tags=["Leads"])


async def _to_response(service: CustomerService, lead) -> LeadResponse:  # noqa: ANN001
    customer = await service.customers.get(lead.customer_id)
    response = LeadResponse.model_validate(lead)
    if customer:
        response.customer_name = customer.name
        response.customer_phone_masked = mask_phone(customer.normalized_phone) or None
    return response


def _lead_not_found() -> NotFoundError:
    """One error for "no such lead" and "not yours".

    Returning 403 for the second case would confirm the lead exists under
    someone else, which is itself a disclosure.
    """
    return NotFoundError("lead not found", user_message="We couldn't find that lead.")


@router.get("", response_model=Page[LeadResponse])
async def list_leads(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("lead:read")],
    params: Annotated[PageParams, Depends()],
    status_filter: Annotated[LeadStatus | None, Query(alias="status")] = None,
) -> Page[LeadResponse]:
    """``LeadRepository.list_leads`` only supports narrowing to a single
    owner (``assigned_user_id``), not an arbitrary set - so an unrestricted
    scope (owner/manager) passes ``None`` and sees every lead, while anyone
    else is restricted to their own.
    """
    repo = LeadRepository(db, principal.business_id)
    service = CustomerService(db, principal.business_id)
    scope = scope_filter(principal.role, principal.user_id)
    assigned_user_id = None if scope.unrestricted else principal.user_id

    rows, total = await repo.list_leads(
        params, status=status_filter, assigned_user_id=assigned_user_id
    )
    return Page.build([await _to_response(service, lead) for lead in rows], total, params)


@router.get("/funnel", response_model=LeadFunnelResponse, summary="Funnel and conversion rate")
async def funnel(
    db: DbDep, principal: Annotated[CurrentUser, requires("lead:read")]
) -> LeadFunnelResponse:
    """``counts_by_status``, ``total_and_converted`` and ``count_conversions``
    take no per-owner filter at all in the current repository implementation -
    the funnel is organization-wide for anyone holding ``lead:read``, same as
    the daily/weekly/monthly reports. Row-level scoping here would need those
    three repository methods extended with an ``assigned_user_id`` parameter,
    not just this endpoint.
    """
    repo = LeadRepository(db, principal.business_id)

    counts = await repo.counts_by_status()
    total, converted = await repo.total_and_converted()

    now = datetime.now(UTC)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_week = start_today - timedelta(days=now.weekday())
    start_month = start_today.replace(day=1)

    return LeadFunnelResponse(
        total_leads=total,
        by_status=counts,
        converted_leads=converted,
        conversion_rate=round((converted / total) * 100, 2) if total else 0.0,
        converted_today=await repo.count_conversions(start_today, now),
        converted_this_week=await repo.count_conversions(start_week, now),
        converted_this_month=await repo.count_conversions(start_month, now),
    )


@router.patch("/{lead_id}/status", response_model=LeadResponse)
async def update_status(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("lead:write")],
    lead_id: uuid.UUID,
    payload: LeadStatusUpdate,
) -> LeadResponse:
    repo = LeadRepository(db, principal.business_id)
    service = CustomerService(db, principal.business_id)
    scope = scope_filter(principal.role, principal.user_id)

    lead = await repo.get_or_404(lead_id)

    # Without this, any member could move anyone's lead through the funnel -
    # including marking a colleague's deal lost.
    if not scope.allows(lead):
        raise _lead_not_found()

    customer = await service.customers.get_or_404(lead.customer_id)

    await service.set_lead_status(
        customer, payload.status, actor_id=principal.user_id, reason=payload.reason
    )
    await AuditRepository(db, principal.business_id).record(
        action="lead.status_changed",
        actor_user_id=principal.user_id,
        entity_type="lead",
        entity_id=lead.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"to": payload.status.value},
    )
    await db.flush()
    return await _to_response(service, lead)


@router.post("/{lead_id}/convert", response_model=LeadResponse, summary="Convert to customer")
async def convert(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("lead:convert")],
    lead_id: uuid.UUID,
    payload: LeadConvertRequest,
) -> LeadResponse:
    repo = LeadRepository(db, principal.business_id)
    service = CustomerService(db, principal.business_id)
    scope = scope_filter(principal.role, principal.user_id)

    lead = await repo.get_or_404(lead_id)

    # Conversion writes a revenue row and attributes it to the caller. Claiming
    # someone else's deal must not be possible.
    if not scope.allows(lead):
        raise _lead_not_found()

    customer = await service.customers.get_or_404(lead.customer_id)

    await service.set_lead_status(
        customer, LeadStatus.CONVERTED, actor_id=principal.user_id, reason=payload.note
    )
    db.add(
        ConversionEvent(
            business_id=principal.business_id,
            customer_id=customer.id,
            lead_id=lead.id,
            value_amount=payload.value_amount,
            currency=payload.currency.upper(),
            converted_by_user_id=principal.user_id,
            note=payload.note,
        )
    )
    await AuditRepository(db, principal.business_id).record(
        action="lead.converted",
        actor_user_id=principal.user_id,
        entity_type="lead",
        entity_id=lead.id,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.flush()
    return await _to_response(service, lead)
