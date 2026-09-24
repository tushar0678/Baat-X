from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.models.enums import FollowUpStatus, FollowUpType
from app.models.followup import FollowUp
from app.repositories.base import TenantRepository

ACTIVE_STATUSES = (FollowUpStatus.PENDING, FollowUpStatus.RESCHEDULED, FollowUpStatus.OVERDUE)


class FollowUpRepository(TenantRepository[FollowUp]):
    model = FollowUp

    async def list_between(
        self,
        start: datetime,
        end: datetime,
        *,
        statuses: tuple[FollowUpStatus, ...] = ACTIVE_STATUSES,
        assigned_user_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[FollowUp]:
        stmt = (
            self.base_query()
            .where(FollowUp.due_at >= start)
            .where(FollowUp.due_at < end)
            .where(FollowUp.status.in_(statuses))
            .order_by(FollowUp.due_at.asc())
            .limit(limit)
        )
        if assigned_user_id:
            stmt = stmt.where(FollowUp.assigned_user_id == assigned_user_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_overdue(
        self, now: datetime, *, assigned_user_id: uuid.UUID | None = None, limit: int = 200
    ) -> list[FollowUp]:
        stmt = (
            self.base_query()
            .where(FollowUp.due_at < now)
            .where(FollowUp.status.in_(ACTIVE_STATUSES))
            .order_by(FollowUp.due_at.asc())
            .limit(limit)
        )
        if assigned_user_id:
            stmt = stmt.where(FollowUp.assigned_user_id == assigned_user_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_recent_completed(
        self, since: datetime, *, assigned_user_id: uuid.UUID | None = None, limit: int = 50
    ) -> list[FollowUp]:
        stmt = (
            self.base_query()
            .where(FollowUp.status == FollowUpStatus.COMPLETED)
            .where(FollowUp.completed_at >= since)
            .order_by(FollowUp.completed_at.desc())
            .limit(limit)
        )
        if assigned_user_id:
            stmt = stmt.where(FollowUp.assigned_user_id == assigned_user_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def next_pending_for_customer(self, customer_id: uuid.UUID) -> FollowUp | None:
        stmt = (
            self.base_query()
            .where(FollowUp.customer_id == customer_id)
            .where(FollowUp.status.in_(ACTIVE_STATUSES))
            .order_by(FollowUp.due_at.asc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def count_created(self, start: datetime, end: datetime) -> int:
        return await self._count(FollowUp.created_at, start, end)

    async def count_completed(self, start: datetime, end: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(FollowUp)
            .where(FollowUp.business_id == self.business_id)
            .where(FollowUp.status == FollowUpStatus.COMPLETED)
            .where(FollowUp.completed_at >= start)
            .where(FollowUp.completed_at < end)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_pending(self, as_of: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(FollowUp)
            .where(FollowUp.business_id == self.business_id)
            .where(FollowUp.status.in_(ACTIVE_STATUSES))
            .where(FollowUp.due_at >= as_of)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_overdue(self, as_of: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(FollowUp)
            .where(FollowUp.business_id == self.business_id)
            .where(FollowUp.status.in_(ACTIVE_STATUSES))
            .where(FollowUp.due_at < as_of)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_callbacks_requested(self, start: datetime, end: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(FollowUp)
            .where(FollowUp.business_id == self.business_id)
            .where(FollowUp.customer_requested_callback.is_(True))
            .where(FollowUp.created_at >= start)
            .where(FollowUp.created_at < end)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_quotations_promised(self, start: datetime, end: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(FollowUp)
            .where(FollowUp.business_id == self.business_id)
            .where(FollowUp.type == FollowUpType.SEND_QUOTATION)
            .where(FollowUp.created_at >= start)
            .where(FollowUp.created_at < end)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def pending_quotations(self, older_than: datetime) -> list[FollowUp]:
        stmt = (
            self.base_query()
            .where(FollowUp.type == FollowUpType.SEND_QUOTATION)
            .where(FollowUp.status.in_(ACTIVE_STATUSES))
            .where(FollowUp.created_at < older_than)
            .order_by(FollowUp.created_at.asc())
            .limit(25)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def due_for_reminder(
        self, window_start: datetime, window_end: datetime
    ) -> list[FollowUp]:
        stmt = (
            self.base_query()
            .where(FollowUp.status.in_(ACTIVE_STATUSES))
            .where(FollowUp.due_at >= window_start)
            .where(FollowUp.due_at < window_end)
            .where(FollowUp.reminder_sent_at.is_(None))
            .limit(500)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _count(self, column, start: datetime, end: datetime) -> int:  # noqa: ANN001
        stmt = (
            select(func.count())
            .select_from(FollowUp)
            .where(FollowUp.business_id == self.business_id)
            .where(column >= start)
            .where(column < end)
        )
        return int((await self.session.execute(stmt)).scalar_one())
