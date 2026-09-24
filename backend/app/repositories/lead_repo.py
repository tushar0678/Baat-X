from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.core.pagination import PageParams
from app.models.crm import ConversionEvent, Lead, LeadStatusTransition
from app.models.enums import LeadStatus
from app.repositories.base import TenantRepository


class LeadRepository(TenantRepository[Lead]):
    model = Lead

    SORTABLE = {"updated_at": Lead.updated_at, "created_at": Lead.created_at, "score": Lead.score}

    async def get_by_customer(self, customer_id: uuid.UUID) -> Lead | None:
        stmt = self.base_query().where(Lead.customer_id == customer_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_leads(
        self,
        params: PageParams,
        *,
        status: LeadStatus | None = None,
        assigned_user_id: uuid.UUID | None = None,
    ) -> tuple[list[Lead], int]:
        stmt = self.base_query()
        if status:
            stmt = stmt.where(Lead.status == status)
        if assigned_user_id:
            stmt = stmt.where(Lead.assigned_user_id == assigned_user_id)
        stmt = self.apply_sort(stmt, params, self.SORTABLE)
        return await self.paginate(stmt, params)

    async def counts_by_status(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> dict[LeadStatus, int]:
        stmt = select(Lead.status, func.count()).where(Lead.business_id == self.business_id)
        if start:
            stmt = stmt.where(Lead.created_at >= start)
        if end:
            stmt = stmt.where(Lead.created_at < end)
        rows = (await self.session.execute(stmt.group_by(Lead.status))).all()
        result = dict.fromkeys(LeadStatus, 0)
        for status, count in rows:
            result[LeadStatus(status)] = int(count)
        return result

    async def record_transition(
        self,
        lead: Lead,
        *,
        from_status: LeadStatus | None,
        to_status: LeadStatus,
        user_id: uuid.UUID | None,
        reason: str | None = None,
    ) -> LeadStatusTransition:
        transition = LeadStatusTransition(
            business_id=self.business_id,
            lead_id=lead.id,
            from_status=from_status,
            to_status=to_status,
            changed_by_user_id=user_id,
            reason=reason,
        )
        self.session.add(transition)
        return transition

    async def count_conversions(self, start: datetime, end: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(ConversionEvent)
            .where(ConversionEvent.business_id == self.business_id)
            .where(ConversionEvent.created_at >= start)
            .where(ConversionEvent.created_at < end)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def total_and_converted(self) -> tuple[int, int]:
        total = await self.count()
        converted_stmt = (
            select(func.count())
            .select_from(Lead)
            .where(Lead.business_id == self.business_id)
            .where(Lead.status == LeadStatus.CONVERTED)
        )
        return total, int((await self.session.execute(converted_stmt)).scalar_one())
