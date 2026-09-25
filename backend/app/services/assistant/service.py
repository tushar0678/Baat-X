"""Natural-language CRM assistant.

The LLM only classifies intent; every answer is produced by a real, scoped SQL
query. Destructive intents return a confirmation token and run only when the
user sends it back.

Scoping is the whole point of this module's plumbing. The assistant is the
easiest place in the product to leak data: a salesperson can simply *ask* for
something they cannot reach through any screen. So every query here - reads,
lookups and writes alike - is filtered by the caller's own ``ScopeFilter``.
There is no "assistant mode" that sees more than the caller does.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import ScopeFilter, VisibilityScope
from app.config.logging import get_logger
from app.core.phone import mask_phone
from app.core.timeparse import resolve_follow_up_datetime
from app.models.conversation import ConversationEvent
from app.models.crm import Customer
from app.models.enums import FollowUpType, LeadStatus, QueryCategory
from app.models.followup import FollowUp
from app.repositories.customer_repo import CustomerRepository
from app.repositories.followup_repo import ACTIVE_STATUSES, FollowUpRepository
from app.schemas.assistant import AssistantQueryRequest, AssistantQueryResponse
from app.schemas.followup import FollowUpCreate
from app.services.ai.base import LLMProvider
from app.services.ai.prompts import ASSISTANT_SYSTEM_PROMPT
from app.services.crm.customer_service import CustomerService
from app.services.reminders.followup_service import FollowUpService

log = get_logger(__name__)

DESTRUCTIVE_INTENTS = {"create_followup", "update_lead_status"}

# Ownership columns, per model. ``assigned_user_id`` is the Lead/FollowUp
# spelling in this codebase - using the wrong name here would silently disable
# the filter rather than raise.
_OWNER_COLUMN = {
    Customer: "owner_user_id",
    FollowUp: "assigned_user_id",
    ConversationEvent: "created_by_user_id",
}


class AssistantService:
    def __init__(
        self,
        session: AsyncSession,
        business_id: uuid.UUID,
        *,
        llm: LLMProvider,
        scope: ScopeFilter,
        timezone: str = "Asia/Kolkata",
    ) -> None:
        self.session = session
        self.business_id = business_id
        self.llm = llm
        self.scope = scope
        self.user_id = scope.user_id
        self.tz = ZoneInfo(timezone)

        self.customers = CustomerRepository(session, business_id)
        self.follow_ups = FollowUpRepository(session, business_id)
        self.customer_service = CustomerService(session, business_id)
        self.follow_up_service = FollowUpService(session, business_id, timezone)

    # ---------------- scoping ----------------

    def _scoped(self, stmt: Select, model) -> Select:  # noqa: ANN001
        """Tenant filter always; ownership filter unless the caller is org-wide.

        Falls back to ``team_id`` when the model carries one, so a team lead
        still sees a record that was reassigned within their team.
        """
        stmt = stmt.where(model.business_id == self.business_id)

        if self.scope.unrestricted:
            return stmt

        allowed = self.scope.user_ids or {self.user_id}
        column_name = _OWNER_COLUMN.get(model)
        column = getattr(model, column_name, None) if column_name else None

        if column is None:
            return stmt

        if self.scope.scope is VisibilityScope.TEAM and self.scope.team_ids:
            team_column = getattr(model, "team_id", None)
            if team_column is not None:
                from sqlalchemy import or_

                return stmt.where(
                    or_(column.in_(allowed), team_column.in_(self.scope.team_ids))
                )

        return stmt.where(column.in_(allowed))

    # ---------------- entry point ----------------

    async def handle(self, request: AssistantQueryRequest) -> AssistantQueryResponse:
        intent, parameters, destructive, restatement = await self._classify(request.query)

        if destructive or intent in DESTRUCTIVE_INTENTS:
            token = _confirm_token(self.business_id, self.user_id, intent, parameters)
            if request.confirm_token != token:
                return AssistantQueryResponse(
                    answer=f"{restatement} Should I go ahead?".strip(),
                    kind="confirmation_required",
                    confirm_token=token,
                )
            return await self._execute(intent, parameters)

        return await self._answer(intent, parameters)

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

                stmt = self._scoped(
                    select(ConversationEvent).where(
                        ConversationEvent.customer_id == customer.id
                    ),
                    ConversationEvent,
                ).order_by(ConversationEvent.occurred_at.desc()).limit(1)

                event = (await self.session.execute(stmt)).scalars().first()
                if event is None:
                    return AssistantQueryResponse(
                        answer=f"No conversation has been recorded for {customer.name} yet.",
                        is_ai_generated=False,
                    )
                return AssistantQueryResponse(
                    answer=(
                        f"Last conversation with {customer.name} on "
                        f"{event.occurred_at:%d %b %Y}: "
                        f"{event.summary or 'no summary recorded'}"
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

                stmt = self._scoped(
                    select(FollowUp).where(
                        FollowUp.due_at >= start,
                        FollowUp.due_at < start + timedelta(days=1),
                        FollowUp.status.in_(ACTIVE_STATUSES),
                    ),
                    FollowUp,
                ).order_by(FollowUp.due_at.asc())

                rows = (await self.session.execute(stmt)).scalars().all()
                return AssistantQueryResponse(
                    answer=f"{len(rows)} follow-up(s) scheduled for {label}.",
                    data=[await self._follow_up_row(f) for f in rows],
                    is_ai_generated=False,
                )

            case "customers_by_budget":
                stmt = self._scoped(select(Customer), Customer)
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

                stmt = self._scoped(
                    select(Customer).where(Customer.lead_status == status), Customer
                ).order_by(Customer.updated_at.desc()).limit(25)

                rows = (await self.session.execute(stmt)).scalars().all()
                return AssistantQueryResponse(
                    answer=f"{len(rows)} customer(s) are marked {status.value}.",
                    data=[self._customer_row(c) for c in rows],
                    is_ai_generated=False,
                )

            case "customers_with_price_concern":
                stmt = self._scoped(
                    select(Customer)
                    .join(ConversationEvent, ConversationEvent.customer_id == Customer.id)
                    .where(
                        ConversationEvent.primary_query_category.in_(
                            [QueryCategory.PRICING, QueryCategory.DISCOUNT]
                        )
                    ),
                    Customer,
                ).order_by(Customer.updated_at.desc()).limit(25)

                rows = (await self.session.execute(stmt)).scalars().unique().all()
                return AssistantQueryResponse(
                    answer=f"{len(rows)} customer(s) raised pricing or discount concerns.",
                    data=[self._customer_row(c) for c in rows],
                    is_ai_generated=False,
                )

            case "customers_requested_callback":
                # Scoped on the follow-up: whoever owes the callback is the one
                # who should be reminded of it.
                stmt = self._scoped(
                    select(FollowUp, Customer)
                    .join(Customer, Customer.id == FollowUp.customer_id)
                    .where(
                        FollowUp.customer_requested_callback.is_(True),
                        FollowUp.status.in_(ACTIVE_STATUSES),
                    ),
                    FollowUp,
                ).order_by(FollowUp.due_at.asc()).limit(25)

                rows = (await self.session.execute(stmt)).all()
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

                # Counts leak too: a total that includes rows the caller can't
                # open still tells them those rows exist.
                converted = await self._count(
                    self._scoped(
                        select(Customer).where(
                            Customer.lead_status == LeadStatus.CONVERTED,
                            Customer.updated_at >= start,
                            Customer.updated_at < end,
                        ),
                        Customer,
                    )
                )
                visible_total = await self._count(self._scoped(select(Customer), Customer))
                all_converted = await self._count(
                    self._scoped(
                        select(Customer).where(Customer.lead_status == LeadStatus.CONVERTED),
                        Customer,
                    )
                )
                rate = round((all_converted / visible_total) * 100, 2) if visible_total else 0.0

                scope_label = {
                    VisibilityScope.ORG: "across the organization",
                    VisibilityScope.TEAM: "across your team",
                    VisibilityScope.OWN: "from your own leads",
                }[self.scope.scope]

                return AssistantQueryResponse(
                    answer=(
                        f"{converted} lead(s) converted in that period {scope_label}. "
                        f"Conversion rate is {rate}%."
                    ),
                    data=[{"converted": converted, "overall_rate": rate}],
                    is_ai_generated=False,
                )

            case "query_summary":
                start, end = self._window(p.get("period", "this_week"))

                stmt = self._scoped(
                    select(ConversationEvent).where(
                        ConversationEvent.occurred_at >= start,
                        ConversationEvent.occurred_at < end,
                    ),
                    ConversationEvent,
                )
                events = (await self.session.execute(stmt)).scalars().all()

                counts: dict[str, int] = {}
                for event in events:
                    for category in event.query_categories or []:
                        counts[str(category)] = counts.get(str(category), 0) + 1

                return AssistantQueryResponse(
                    answer=(
                        f"{len(events)} conversation(s) recorded in that period, "
                        f"with {sum(counts.values())} customer queries."
                    ),
                    data=[{"by_category": counts}],
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

        # Belt and braces: _find_customer is already scoped, but a write must
        # never rest on a single upstream filter being correct.
        if not self.scope.allows(customer):
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
        """Name lookup, restricted to what the caller may see.

        Deliberately not the repository's fuzzy search: that is tenant-scoped
        only, so a colleague's customer would resolve by name. Here an
        out-of-scope name simply doesn't exist.
        """
        if not name:
            return None

        stmt = self._scoped(
            select(Customer).where(Customer.name.ilike(f"%{str(name).strip()}%")), Customer
        ).order_by(Customer.updated_at.desc()).limit(1)

        return (await self.session.execute(stmt)).scalars().first()

    async def _count(self, stmt: Select) -> int:
        from sqlalchemy import func

        return await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

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


def _confirm_token(
    business_id: uuid.UUID, user_id: uuid.UUID | None, intent: str, parameters: dict
) -> str:
    """Deterministic per (tenant, user, intent, params).

    ``user_id`` is in the hash so a token cannot be replayed by a different
    member to execute an action they were never offered.
    """
    raw = json.dumps(
        {"b": str(business_id), "u": str(user_id), "i": intent, "p": parameters},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _not_found(name: str | None) -> AssistantQueryResponse:
    """One message for "no such customer" and "not yours".

    Distinguishing the two would confirm the customer exists elsewhere in the
    organization, which is itself a disclosure.
    """
    return AssistantQueryResponse(
        answer=(
            f"I couldn't find a customer called {name}."
            if name
            else "Which customer did you mean?"
        ),
        kind="confirmation_required",
    )
