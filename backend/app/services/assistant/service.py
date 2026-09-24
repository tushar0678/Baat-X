"""Natural-language CRM assistant.

The LLM only classifies intent; every answer is produced by a real, tenant-scoped
SQL query. Destructive intents (creating a follow-up, changing a lead status)
return a confirmation token and are executed only when the user sends it back.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging import get_logger
from app.core.phone import mask_phone
from app.core.timeparse import resolve_follow_up_datetime
from app.models.conversation import ConversationEvent
from app.models.crm import Customer
from app.models.enums import FollowUpType, LeadStatus, QueryCategory
from app.models.followup import FollowUp
from app.repositories.customer_repo import CustomerRepository
from app.repositories.followup_repo import ACTIVE_STATUSES, FollowUpRepository
from app.repositories.lead_repo import LeadRepository
from app.schemas.assistant import AssistantAction, AssistantQueryRequest, AssistantQueryResponse
from app.schemas.followup import FollowUpCreate
from app.services.ai.base import LLMProvider
from app.services.ai.prompts import ASSISTANT_SYSTEM_PROMPT
from app.services.crm.customer_service import CustomerService
from app.services.reminders.followup_service import FollowUpService
from app.services.reports.report_service import ReportService

log = get_logger(__name__)

DESTRUCTIVE_INTENTS = {"create_followup", "update_lead_status"}


class AssistantService:
    def __init__(
        self,
        session: AsyncSession,
        business_id: uuid.UUID,
        *,
        llm: LLMProvider,
        timezone: str = "Asia/Kolkata",
        user_id: uuid.UUID | None = None,
        restrict_to_user: bool = False,
    ) -> None:
        self.session = session
        self.business_id = business_id
        self.llm = llm
        self.tz = ZoneInfo(timezone)
        self.user_id = user_id
        self.restrict = restrict_to_user
        self.customers = CustomerRepository(session, business_id)
        self.follow_ups = FollowUpRepository(session, business_id)
        self.leads = LeadRepository(session, business_id)
        self.customer_service = CustomerService(session, business_id)
        self.follow_up_service = FollowUpService(session, business_id, timezone)
        self.reports = ReportService(session, business_id, timezone=timezone, llm=llm)

    async def handle(self, request: AssistantQueryRequest) -> AssistantQueryResponse:
        intent, parameters, destructive, restatement = await self._classify(request.query)

        if destructive or intent in DESTRUCTIVE_INTENTS:
            token = _confirm_token(self.business_id, intent, parameters)
            if request.confirm_token != token:
                return AssistantQueryResponse(
                    answer=f"{restatement} Should I go ahead?".strip(),
                    kind="confirmation_required",
                    action=AssistantAction(
                        intent=intent,
                        description=restatement,
                        parameters=parameters,
                        destructive=True,
                    ),
                    confirm_token=token,
                )
            return await self._execute(intent, parameters)

        return await self._answer(intent, parameters)

    # ---------------- intent ----------------
    async def _classify(self, query: str) -> tuple[str, dict, bool, str]:
        try:
            result = await self.llm.complete_json(
                system_prompt=ASSISTANT_SYSTEM_PROMPT,
                user_prompt=f"User request:\n{query[:1000]}",
                max_output_tokens=400,
            )
            parsed = json.loads(result.content or "{}")
            return (
                str(parsed.get("intent") or "unsupported"),
                dict(parsed.get("parameters") or {}),
                bool(parsed.get("destructive")),
                str(parsed.get("restatement") or ""),
            )
        except Exception:  # noqa: BLE001
            log.info("assistant_classify_failed")
            return "unsupported", {}, False, ""

    # ---------------- read intents ----------------
    async def _answer(self, intent: str, p: dict) -> AssistantQueryResponse:
        now = datetime.now(self.tz)

        match intent:
            case "customer_last_conversation":
                customer = await self._find_customer(p.get("customer_name"))
                if customer is None:
                    return _not_found(p.get("customer_name"))
                stmt = (
                    select(ConversationEvent)
                    .where(ConversationEvent.business_id == self.business_id)
                    .where(ConversationEvent.customer_id == customer.id)
                    .order_by(ConversationEvent.occurred_at.desc())
                    .limit(1)
                )
                event = (await self.session.execute(stmt)).scalars().first()
                if event is None:
                    return AssistantQueryResponse(
                        answer=f"No conversation has been recorded for {customer.name} yet.",
                        is_ai_generated=False,
                    )
                return AssistantQueryResponse(
                    answer=(
                        f"Last conversation with {customer.name} on "
                        f"{event.occurred_at:%d %b %Y}: {event.summary or 'no summary recorded'}"
                    ),
                    data=[{"highlights": event.highlights or {}, "at": str(event.occurred_at)}],
                    is_ai_generated=False,
                )

            case "todays_followups" | "followups_on_date":
                expression = p.get("date_expression")
                if intent == "todays_followups" or not expression:
                    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    label = "today"
                else:
                    resolved = resolve_follow_up_datetime(
                        expression, now=now, timezone=str(self.tz)
                    )
                    if resolved.due_at is None:
                        return AssistantQueryResponse(
                            answer="I couldn't work out that date. Which day did you mean?",
                            kind="confirmation_required",
                        )
                    start = resolved.due_at.replace(hour=0, minute=0, second=0, microsecond=0)
                    label = f"{start:%A, %d %b}"
                rows = await self.follow_ups.list_between(
                    start,
                    start + timedelta(days=1),
                    assigned_user_id=self.user_id if self.restrict else None,
                )
                return AssistantQueryResponse(
                    answer=f"{len(rows)} follow-up(s) scheduled for {label}.",
                    data=[await self._follow_up_row(f) for f in rows],
                    is_ai_generated=False,
                )

            case "customers_by_budget":
                stmt = select(Customer).where(Customer.business_id == self.business_id)
                if (minimum := p.get("min_amount")) is not None:
                    stmt = stmt.where(Customer.budget_max >= Decimal(str(minimum)))
                if (maximum := p.get("max_amount")) is not None:
                    stmt = stmt.where(Customer.budget_min <= Decimal(str(maximum)))
                rows = (
                    await self.session.execute(
                        stmt.order_by(Customer.budget_max.desc().nullslast()).limit(25)
                    )
                ).scalars().all()
                return AssistantQueryResponse(
                    answer=f"{len(rows)} customer(s) match that budget.",
                    data=[self._customer_row(c) for c in rows],
                    is_ai_generated=False,
                )

            case "customers_by_status":
                try:
                    status = LeadStatus(str(p.get("status", "")).lower())
                except ValueError:
                    return AssistantQueryResponse(
                        answer="Which status did you mean - new, interested, hot, or converted?",
                        kind="confirmation_required",
                    )
                rows = (
                    await self.session.execute(
                        select(Customer)
                        .where(Customer.business_id == self.business_id)
                        .where(Customer.lead_status == status)
                        .order_by(Customer.updated_at.desc())
                        .limit(25)
                    )
                ).scalars().all()
                return AssistantQueryResponse(
                    answer=f"{len(rows)} customer(s) are marked {status.value}.",
                    data=[self._customer_row(c) for c in rows],
                    is_ai_generated=False,
                )

            case "customers_with_price_concern":
                rows = (
                    await self.session.execute(
                        select(Customer)
                        .join(ConversationEvent, ConversationEvent.customer_id == Customer.id)
                        .where(Customer.business_id == self.business_id)
                        .where(
                            ConversationEvent.primary_query_category.in_(
                                [QueryCategory.PRICING, QueryCategory.DISCOUNT]
                            )
                        )
                        .order_by(Customer.updated_at.desc())
                        .limit(25)
                    )
                ).scalars().unique().all()
                return AssistantQueryResponse(
                    answer=f"{len(rows)} customer(s) raised pricing or discount concerns.",
                    data=[self._customer_row(c) for c in rows],
                    is_ai_generated=False,
                )

            case "customers_requested_callback":
                rows = (
                    await self.session.execute(
                        select(FollowUp, Customer)
                        .join(Customer, Customer.id == FollowUp.customer_id)
                        .where(FollowUp.business_id == self.business_id)
                        .where(FollowUp.customer_requested_callback.is_(True))
                        .where(FollowUp.status.in_(ACTIVE_STATUSES))
                        .order_by(FollowUp.due_at.asc())
                        .limit(25)
                    )
                ).all()
                return AssistantQueryResponse(
                    answer=f"{len(rows)} customer(s) have requested a callback.",
                    data=[
                        {**self._customer_row(customer), "due_at": str(follow_up.due_at)}
                        for follow_up, customer in rows
                    ],
                    is_ai_generated=False,
                )

            case "conversion_count":
                start, end = self._window(p.get("period", "this_month"))
                count = await self.leads.count_conversions(start, end)
                total, converted = await self.leads.total_and_converted()
                rate = round((converted / total) * 100, 2) if total else 0.0
                return AssistantQueryResponse(
                    answer=(
                        f"{count} lead(s) converted in that period. "
                        f"Overall conversion rate is {rate}%."
                    ),
                    data=[{"converted": count, "overall_rate": rate}],
                    is_ai_generated=False,
                )

            case "query_summary":
                period = p.get("period", "this_week")
                report = (
                    await self.reports.daily(with_insights=False)
                    if period == "today"
                    else await self.reports.period("weekly", with_insights=False)
                )
                queries = report.queries
                return AssistantQueryResponse(
                    answer=(
                        f"{queries.total_queries} customer queries recorded - "
                        f"{queries.price_concerns} about price, "
                        f"{queries.availability_queries} about availability, "
                        f"{queries.quotations_requested} quotation requests."
                    ),
                    data=[{"by_category": {k.value: v for k, v in queries.by_category.items()}}],
                    is_ai_generated=False,
                )

            case _:
                return AssistantQueryResponse(
                    answer=(
                        "I can look up customers, follow-ups, conversions and query summaries, "
                        "or create a follow-up for you. Could you rephrase that?"
                    ),
                    kind="unsupported",
                )

    # ---------------- write intents ----------------
    async def _execute(self, intent: str, p: dict) -> AssistantQueryResponse:
        customer = await self._find_customer(p.get("customer_name"))
        if customer is None:
            return _not_found(p.get("customer_name"))

        if intent == "create_followup":
            resolved = resolve_follow_up_datetime(
                p.get("date_expression"), now=datetime.now(self.tz), timezone=str(self.tz)
            )
            if resolved.due_at is None:
                return AssistantQueryResponse(
                    answer="I couldn't work out that date. Which day should I set?",
                    kind="confirmation_required",
                )
            follow_up = await self.follow_up_service.create(
                FollowUpCreate(
                    customer_id=customer.id,
                    type=FollowUpType.CALL_CUSTOMER,
                    title=str(p.get("action") or "Call customer"),
                    due_at=resolved.due_at,
                    due_time_known=resolved.time_known,
                    reason="Created from the BaatX assistant",
                ),
                actor_id=self.user_id,
            )
            return AssistantQueryResponse(
                answer=(
                    f"Follow-up created for {customer.name} on "
                    f"{resolved.due_at:%A, %d %b at %I:%M %p}."
                ),
                kind="action_executed",
                affected_ids=[follow_up.id],
                is_ai_generated=False,
            )

        if intent == "update_lead_status":
            try:
                status = LeadStatus(str(p.get("status", "")).lower())
            except ValueError:
                return AssistantQueryResponse(
                    answer="Which status should I set?", kind="confirmation_required"
                )
            await self.customer_service.set_lead_status(
                customer, status, actor_id=self.user_id, reason="Assistant update"
            )
            return AssistantQueryResponse(
                answer=f"{customer.name}'s status is now {status.value}.",
                kind="action_executed",
                affected_ids=[customer.id],
                is_ai_generated=False,
            )

        return AssistantQueryResponse(answer="I can't do that yet.", kind="unsupported")

    # ---------------- helpers ----------------
    async def _find_customer(self, name: str | None) -> Customer | None:
        if not name:
            return None
        matches = await self.customers.find_by_name_fuzzy(str(name), limit=1)
        return matches[0] if matches else None

    def _window(self, period: str) -> tuple[datetime, datetime]:
        now = datetime.now(self.tz)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        match period:
            case "today":
                return start_of_day, start_of_day + timedelta(days=1)
            case "this_week":
                start = start_of_day - timedelta(days=now.weekday())
                return start, start + timedelta(days=7)
            case _:
                start = start_of_day.replace(day=1)
                return start, (start + timedelta(days=32)).replace(day=1)

    def _customer_row(self, customer: Customer) -> dict:
        return {
            "customer_id": str(customer.id),
            "name": customer.name,
            "phone_masked": mask_phone(customer.normalized_phone),
            "requirement": customer.requirement,
            "budget_max": float(customer.budget_max) if customer.budget_max else None,
            "status": customer.lead_status,
        }

    async def _follow_up_row(self, follow_up: FollowUp) -> dict:
        customer = await self.customers.get(follow_up.customer_id)
        return {
            "follow_up_id": str(follow_up.id),
            "customer_id": str(follow_up.customer_id),
            "customer_name": customer.name if customer else None,
            "action": follow_up.title,
            "due_at": str(follow_up.due_at),
            "status": follow_up.status,
        }


def _confirm_token(business_id: uuid.UUID, intent: str, parameters: dict) -> str:
    """Deterministic per (tenant, intent, params) so a replay can't be repurposed."""
    raw = json.dumps(
        {"b": str(business_id), "i": intent, "p": parameters}, sort_keys=True, default=str
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _not_found(name: str | None) -> AssistantQueryResponse:
    return AssistantQueryResponse(
        answer=(
            f"I couldn't find a customer called {name}."
            if name
            else "Which customer did you mean?"
        ),
        kind="confirmation_required",
    )
