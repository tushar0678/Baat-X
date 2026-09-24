from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging import get_logger
from app.core.dt import is_past
from app.core.errors import ValidationError
from app.core.phone import mask_phone
from app.models.crm import Customer
from app.models.enums import FollowUpStatus, FollowUpType, LeadStatus, NotificationType
from app.models.followup import FollowUp
from app.repositories.customer_repo import CustomerRepository
from app.repositories.followup_repo import ACTIVE_STATUSES, FollowUpRepository
from app.schemas.followup import (
    FollowUpBoard,
    FollowUpCreate,
    FollowUpResponse,
    FollowUpUpdate,
    SmartSuggestion,
)
from app.services.notifications.service import NotificationService

log = get_logger(__name__)

FOLLOW_UP_TITLES: dict[FollowUpType, str] = {
    FollowUpType.CALL_CUSTOMER: "Call customer",
    FollowUpType.WHATSAPP_CUSTOMER: "WhatsApp customer",
    FollowUpType.SEND_QUOTATION: "Send quotation",
    FollowUpType.SEND_EMAIL: "Send email",
    FollowUpType.MEET_CUSTOMER: "Meet customer",
    FollowUpType.CHECK_AVAILABILITY: "Check availability",
    FollowUpType.DISCUSS_PRICE: "Discuss price",
    FollowUpType.SCHEDULE_TEST_DRIVE: "Schedule test drive",
    FollowUpType.SHOW_PROPERTY: "Show property",
    FollowUpType.SEND_DOCUMENT: "Send document",
    FollowUpType.PAYMENT_FOLLOW_UP: "Payment follow-up",
    FollowUpType.GENERAL_FOLLOW_UP: "General follow-up",
    FollowUpType.OTHER: "Follow-up",
}


class FollowUpService:
    def __init__(
        self, session: AsyncSession, business_id: uuid.UUID, timezone: str = "Asia/Kolkata"
    ) -> None:
        self.session = session
        self.business_id = business_id
        self.tz = ZoneInfo(timezone)
        self.repo = FollowUpRepository(session, business_id)
        self.customers = CustomerRepository(session, business_id)
        self.notifications = NotificationService(session, business_id)

    # ---------------- creation ----------------
    async def create(
        self,
        data: FollowUpCreate,
        *,
        actor_id: uuid.UUID | None,
        created_by_ai: bool = False,
        confidence: float | None = None,
    ) -> FollowUp:
        customer = await self.customers.get_or_404(data.customer_id)
        if data.due_at is None:
            raise ValidationError(
                "missing due date",
                user_message="Please choose when this follow-up should happen.",
            )
        follow_up = FollowUp(
            business_id=self.business_id,
            customer_id=customer.id,
            type=data.type,
            title=data.title or FOLLOW_UP_TITLES.get(data.type, "Follow-up"),
            reason=data.reason,
            notes=data.notes,
            due_at=data.due_at,
            due_time_known=data.due_time_known,
            assigned_user_id=data.assigned_user_id or customer.owner_user_id or actor_id,
            created_by_ai=created_by_ai,
            confidence=confidence,
            customer_requested_callback=data.customer_requested_callback,
        )
        self.session.add(follow_up)
        await self.session.flush()
        await self._sync_customer_next_follow_up(customer)

        if data.customer_requested_callback:
            await self.notifications.create(
                user_id=follow_up.assigned_user_id,
                type=NotificationType.CUSTOMER_REQUESTED_CALLBACK,
                title="Callback requested",
                body=f"{customer.name or 'Customer'} asked for a callback.",
                customer_id=customer.id,
                follow_up_id=follow_up.id,
                dedupe_key=f"callback:{follow_up.id}",
            )
        return follow_up

    async def update(
        self, follow_up_id: uuid.UUID, data: FollowUpUpdate, *, actor_id: uuid.UUID | None
    ) -> FollowUp:
        follow_up = await self.repo.get_or_404(follow_up_id)
        changes = data.model_dump(exclude_unset=True)

        if (new_due := changes.get("due_at")) is not None and new_due != follow_up.due_at:
            follow_up.rescheduled_from = follow_up.due_at
            follow_up.due_at = new_due
            follow_up.reminder_sent_at = None
            if "status" not in changes:
                follow_up.status = FollowUpStatus.RESCHEDULED

        if (status := changes.get("status")) is not None:
            follow_up.status = FollowUpStatus(status)
            if follow_up.status == FollowUpStatus.COMPLETED:
                follow_up.completed_at = datetime.now(UTC)

        for key in ("type", "title", "notes", "assigned_user_id"):
            if key in changes and changes[key] is not None:
                setattr(follow_up, key, changes[key])

        await self.session.flush()
        customer = await self.customers.get(follow_up.customer_id)
        if customer:
            await self._sync_customer_next_follow_up(customer)
        return follow_up

    async def _sync_customer_next_follow_up(self, customer: Customer) -> None:
        nxt = await self.repo.next_pending_for_customer(customer.id)
        customer.next_follow_up_at = nxt.due_at if nxt else None

    # ---------------- board ----------------
    async def board(self, *, assigned_user_id: uuid.UUID | None) -> FollowUpBoard:
        now = datetime.now(self.tz)
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_tomorrow = start_today + timedelta(days=1)
        start_day_after = start_today + timedelta(days=2)
        horizon = start_today + timedelta(days=30)

        today = await self.repo.list_between(
            start_today, start_tomorrow, assigned_user_id=assigned_user_id
        )
        tomorrow = await self.repo.list_between(
            start_tomorrow, start_day_after, assigned_user_id=assigned_user_id
        )
        upcoming = await self.repo.list_between(
            start_day_after, horizon, assigned_user_id=assigned_user_id
        )
        overdue = await self.repo.list_overdue(now, assigned_user_id=assigned_user_id)
        completed = await self.repo.list_recent_completed(
            now - timedelta(days=7), assigned_user_id=assigned_user_id
        )

        # `today` must not contain items whose time has already passed - those are overdue.
        overdue_ids = {f.id for f in overdue}
        today = [f for f in today if f.id not in overdue_ids]

        return FollowUpBoard(
            today=[await self.to_response(f, now) for f in today],
            tomorrow=[await self.to_response(f, now) for f in tomorrow],
            upcoming=[await self.to_response(f, now) for f in upcoming],
            overdue=[await self.to_response(f, now) for f in overdue],
            completed=[await self.to_response(f, now) for f in completed],
            counts={
                "today": len(today),
                "tomorrow": len(tomorrow),
                "upcoming": len(upcoming),
                "overdue": len(overdue),
                "completed": len(completed),
            },
        )

    async def to_response(
        self, follow_up: FollowUp, now: datetime | None = None
    ) -> FollowUpResponse:
        now = now or datetime.now(self.tz)
        customer = await self.customers.get(follow_up.customer_id)
        response = FollowUpResponse.model_validate(follow_up)
        response.customer_name = customer.name if customer else None
        response.customer_phone_masked = (
            mask_phone(customer.normalized_phone or customer.phone) or None if customer else None
        )
        response.is_overdue = follow_up.status in ACTIVE_STATUSES and is_past(
            follow_up.due_at, now
        )
        return response

    # ---------------- smart follow-up intelligence (§16) ----------------
    async def smart_suggestions(self) -> list[SmartSuggestion]:
        """Detect gaps and propose reminders. Never contacts a customer."""
        now = datetime.now(self.tz)
        suggestions: list[SmartSuggestion] = []

        for customer in await self.customers.hot_leads_without_recent_contact(
            now - timedelta(days=3)
        ):
            suggestions.append(
                SmartSuggestion(
                    kind="hot_lead_no_recent_contact",
                    customer_id=customer.id,
                    customer_name=customer.name,
                    message=(
                        f"{customer.name or 'A hot lead'} hasn't been contacted in 3+ days "
                        "and has no next action."
                    ),
                    suggested_type=FollowUpType.CALL_CUSTOMER,
                    suggested_due_at=now + timedelta(hours=4),
                )
            )

        for follow_up in await self.repo.pending_quotations(now - timedelta(days=1)):
            customer = await self.customers.get(follow_up.customer_id)
            suggestions.append(
                SmartSuggestion(
                    kind="quotation_promised_not_sent",
                    customer_id=follow_up.customer_id,
                    customer_name=customer.name if customer else None,
                    message="A quotation was promised but hasn't been marked as sent.",
                    suggested_type=FollowUpType.SEND_QUOTATION,
                    suggested_due_at=now + timedelta(hours=2),
                )
            )

        overdue_callbacks = [
            f for f in await self.repo.list_overdue(now) if f.customer_requested_callback
        ]
        for follow_up in overdue_callbacks[:10]:
            customer = await self.customers.get(follow_up.customer_id)
            suggestions.append(
                SmartSuggestion(
                    kind="callback_requested_not_completed",
                    customer_id=follow_up.customer_id,
                    customer_name=customer.name if customer else None,
                    message="The customer asked for a callback and it's now overdue.",
                    suggested_type=FollowUpType.CALL_CUSTOMER,
                    suggested_due_at=now + timedelta(hours=1),
                )
            )
        return suggestions[:25]

    # ---------------- reminder sweep (worker) ----------------
    async def sweep_due_reminders(self) -> int:
        """Mark overdue items and emit de-duplicated reminder notifications."""
        now = datetime.now(self.tz)
        created = 0

        for follow_up in await self.repo.list_overdue(now):
            if follow_up.status != FollowUpStatus.OVERDUE:
                follow_up.status = FollowUpStatus.OVERDUE
            customer = await self.customers.get(follow_up.customer_id)
            notification = await self.notifications.create(
                user_id=follow_up.assigned_user_id,
                type=NotificationType.FOLLOW_UP_OVERDUE,
                title="Overdue follow-up",
                body=f"{follow_up.title} - {customer.name if customer else 'customer'}",
                customer_id=follow_up.customer_id,
                follow_up_id=follow_up.id,
                dedupe_key=f"overdue:{follow_up.id}:{now:%Y-%m-%d}",
            )
            created += int(notification is not None)

        for follow_up in await self.repo.due_for_reminder(now, now + timedelta(minutes=30)):
            customer = await self.customers.get(follow_up.customer_id)
            notification = await self.notifications.create(
                user_id=follow_up.assigned_user_id,
                type=_reminder_type(FollowUpType(follow_up.type)),
                title="Follow-up due soon",
                body=f"{follow_up.title} - {customer.name if customer else 'customer'}",
                customer_id=follow_up.customer_id,
                follow_up_id=follow_up.id,
                dedupe_key=f"due:{follow_up.id}",
            )
            if notification is not None:
                follow_up.reminder_sent_at = now
                created += 1

        await self.session.flush()
        return created


def _reminder_type(follow_up_type: FollowUpType) -> NotificationType:
    match follow_up_type:
        case FollowUpType.SEND_QUOTATION:
            return NotificationType.QUOTATION_REMINDER
        case FollowUpType.MEET_CUSTOMER | FollowUpType.SHOW_PROPERTY:
            return NotificationType.MEETING_REMINDER
        case FollowUpType.PAYMENT_FOLLOW_UP:
            return NotificationType.PAYMENT_FOLLOW_UP
        case FollowUpType.CALL_CUSTOMER:
            return NotificationType.CALLBACK_REMINDER
        case _:
            return NotificationType.FOLLOW_UP_DUE


def infer_status_from_followup(current: LeadStatus) -> LeadStatus:
    """A pending follow-up moves an early-stage lead into the follow-up bucket."""
    if current in (LeadStatus.NEW, LeadStatus.CONTACTED):
        return LeadStatus.FOLLOW_UP
    return current
