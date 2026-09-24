from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging import get_logger
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams
from app.core.phone import mask_phone, normalize_phone
from app.models.crm import Customer, Lead
from app.models.enums import ConversationSource, LeadStatus
from app.models.followup import FollowUp
from app.repositories.customer_repo import CustomerRepository
from app.repositories.followup_repo import FollowUpRepository
from app.repositories.job_repo import ConversationEventRepository
from app.repositories.lead_repo import LeadRepository
from app.schemas.crm import (
    CustomerCreate,
    CustomerListFilters,
    CustomerResponse,
    CustomerTimelineResponse,
    CustomerUpdate,
    DuplicateCandidate,
    TimelineEntry,
)

log = get_logger(__name__)


class CustomerService:
    def __init__(self, session: AsyncSession, business_id: uuid.UUID, country_code: str = "IN"):
        self.session = session
        self.business_id = business_id
        self.country_code = country_code
        self.customers = CustomerRepository(session, business_id)
        self.leads = LeadRepository(session, business_id)
        self.events = ConversationEventRepository(session, business_id)
        self.follow_ups = FollowUpRepository(session, business_id)

    # ---------------- identity ----------------
    async def resolve_or_create(
        self,
        *,
        phone: str | None,
        name: str | None,
        customer_id: uuid.UUID | None = None,
        source: ConversationSource = ConversationSource.MANUAL,
        owner_user_id: uuid.UUID | None = None,
        create_if_missing: bool = True,
    ) -> tuple[Customer | None, bool, list[DuplicateCandidate]]:
        """Return (customer, matched_existing, duplicate_candidates).

        Identity is (business_id, normalized_phone). Without a phone number we
        never auto-merge - we surface candidates and let the user decide.
        """
        if customer_id is not None:
            customer = await self.customers.get_or_404(customer_id)
            return customer, True, []

        normalized = normalize_phone(phone, self.country_code) if phone else None
        if normalized:
            existing = await self.customers.get_by_normalized_phone(normalized)
            if existing:
                return existing, True, []
            if not create_if_missing:
                return None, False, []
            customer = Customer(
                business_id=self.business_id,
                name=name,
                phone=phone,
                normalized_phone=normalized,
                source=source,
                owner_user_id=owner_user_id,
            )
            self.session.add(customer)
            try:
                await self.session.flush()
            except IntegrityError:
                # Concurrent insert of the same identity - take the winner's row.
                await self.session.rollback()
                existing = await self.customers.get_by_normalized_phone(normalized)
                if existing is None:
                    raise
                return existing, True, []
            await self._ensure_lead(customer, source=source, owner_user_id=owner_user_id)
            return customer, False, []

        candidates: list[DuplicateCandidate] = []
        if name:
            for match in await self.customers.find_by_name_fuzzy(name):
                candidates.append(
                    DuplicateCandidate(
                        customer_id=match.id,
                        name=match.name,
                        phone_masked=mask_phone(match.normalized_phone) or None,
                        last_interaction_at=match.last_interaction_at,
                        match_reason="Similar name",
                    )
                )
        if not create_if_missing:
            return None, False, candidates

        customer = Customer(
            business_id=self.business_id, name=name, source=source, owner_user_id=owner_user_id
        )
        self.session.add(customer)
        await self.session.flush()
        await self._ensure_lead(customer, source=source, owner_user_id=owner_user_id)
        return customer, False, candidates

    async def _ensure_lead(
        self, customer: Customer, *, source: ConversationSource, owner_user_id: uuid.UUID | None
    ) -> Lead:
        lead = await self.leads.get_by_customer(customer.id)
        if lead is None:
            lead = Lead(
                business_id=self.business_id,
                customer_id=customer.id,
                status=customer.lead_status,
                score=customer.lead_score,
                source=source,
                assigned_user_id=owner_user_id or customer.owner_user_id,
            )
            self.session.add(lead)
            await self.session.flush()
            await self.leads.record_transition(
                lead, from_status=None, to_status=lead.status, user_id=owner_user_id
            )
        return lead

    # ---------------- CRUD ----------------
    async def create(self, data: CustomerCreate, *, actor_id: uuid.UUID | None) -> Customer:
        normalized = normalize_phone(data.phone, self.country_code) if data.phone else None
        if normalized:
            existing = await self.customers.get_by_normalized_phone(normalized)
            if existing:
                raise ConflictError(
                    "duplicate customer",
                    user_message="A customer with this phone number already exists.",
                    details={"customer_id": str(existing.id)},
                )
        payload = data.model_dump(exclude_unset=True)
        payload.pop("phone", None)
        owner = payload.pop("owner_user_id", None) or actor_id
        customer = Customer(
            business_id=self.business_id,
            phone=data.phone,
            normalized_phone=normalized,
            owner_user_id=owner,
            **payload,
        )
        customer.field_confidence = {
            key: 1.0 for key, value in payload.items() if value is not None
        }
        self.session.add(customer)
        await self.session.flush()
        await self._ensure_lead(customer, source=data.source, owner_user_id=owner)
        return customer

    async def update(
        self, customer_id: uuid.UUID, data: CustomerUpdate, *, actor_id: uuid.UUID | None
    ) -> Customer:
        customer = await self.customers.get_or_404(customer_id)
        changes = data.model_dump(exclude_unset=True)

        if "phone" in changes:
            normalized = normalize_phone(changes["phone"], self.country_code)
            if changes["phone"] and not normalized:
                raise ValidationError(
                    "invalid phone", user_message="Please enter a valid phone number."
                )
            if normalized and normalized != customer.normalized_phone:
                clash = await self.customers.get_by_normalized_phone(normalized)
                if clash and clash.id != customer.id:
                    raise ConflictError(
                        "phone already used",
                        user_message="Another customer already uses this phone number.",
                        details={"customer_id": str(clash.id)},
                    )
            customer.normalized_phone = normalized

        confidence = dict(customer.field_confidence or {})
        new_status = changes.pop("lead_status", None)
        for key, value in changes.items():
            setattr(customer, key, value)
            if value is not None:
                confidence[key] = 1.0  # human edits are authoritative
        customer.field_confidence = confidence

        if new_status:
            await self.set_lead_status(customer, LeadStatus(new_status), actor_id=actor_id)
        await self.session.flush()
        return customer

    async def set_lead_status(
        self,
        customer: Customer,
        status: LeadStatus,
        *,
        actor_id: uuid.UUID | None,
        reason: str | None = None,
    ) -> Lead:
        lead = await self._ensure_lead(
            customer, source=customer.source, owner_user_id=customer.owner_user_id
        )
        previous = LeadStatus(lead.status)
        if previous == status:
            return lead
        lead.status = status
        customer.lead_status = status
        if status == LeadStatus.CONVERTED:
            lead.converted_at = datetime.now(UTC)
        await self.leads.record_transition(
            lead, from_status=previous, to_status=status, user_id=actor_id, reason=reason
        )
        return lead

    async def list_customers(
        self,
        filters: CustomerListFilters,
        params: PageParams,
        *,
        restrict_to_user_id: uuid.UUID | None,
    ) -> Page[CustomerResponse]:
        rows, total = await self.customers.list_customers(
            filters, params, restrict_to_user_id=restrict_to_user_id
        )
        return Page.build([self.to_response(row) for row in rows], total, params)

    @staticmethod
    def to_response(customer: Customer) -> CustomerResponse:
        response = CustomerResponse.model_validate(customer)
        response.phone_masked = mask_phone(customer.normalized_phone or customer.phone) or None
        return response

    # ---------------- timeline ----------------
    async def timeline(self, customer_id: uuid.UUID, limit: int = 100) -> CustomerTimelineResponse:
        customer = await self.customers.get(customer_id)
        if customer is None:
            raise NotFoundError("customer not found")

        entries: list[TimelineEntry] = []
        for event in await self.events.for_customer(customer_id, limit=limit):
            entries.append(
                TimelineEntry(
                    id=event.id,
                    occurred_at=event.occurred_at,
                    kind="conversation",
                    title=event.title,
                    summary=event.summary,
                    highlights=event.highlights,
                    source=event.source,
                    primary_query_category=event.primary_query_category,
                )
            )

        stmt = (
            self.follow_ups.base_query()
            .where(FollowUp.customer_id == customer_id)
            .order_by(FollowUp.due_at.desc())
            .limit(limit)
        )
        for follow_up in (await self.session.execute(stmt)).scalars().all():
            entries.append(
                TimelineEntry(
                    id=follow_up.id,
                    occurred_at=follow_up.created_at,
                    kind="follow_up_created",
                    title="Reminder Created",
                    summary=f"{follow_up.title} - due {follow_up.due_at:%d %b %Y %H:%M}",
                )
            )
            if follow_up.completed_at:
                entries.append(
                    TimelineEntry(
                        id=follow_up.id,
                        occurred_at=follow_up.completed_at,
                        kind="follow_up_completed",
                        title="Follow-up Completed",
                        summary=follow_up.title,
                    )
                )

        entries.sort(key=lambda e: e.occurred_at, reverse=True)
        return CustomerTimelineResponse(
            customer_id=customer.id,
            name=customer.name,
            phone_masked=mask_phone(customer.normalized_phone or customer.phone) or None,
            entries=entries[:limit],
        )
