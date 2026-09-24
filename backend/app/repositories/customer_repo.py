from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, or_, select

from app.core.pagination import PageParams
from app.models.crm import Customer
from app.models.enums import LeadStatus
from app.repositories.base import TenantRepository
from app.schemas.crm import CustomerListFilters


class CustomerRepository(TenantRepository[Customer]):
    model = Customer

    SORTABLE = {
        "updated_at": Customer.updated_at,
        "created_at": Customer.created_at,
        "last_interaction_at": Customer.last_interaction_at,
        "next_follow_up_at": Customer.next_follow_up_at,
        "lead_score": Customer.lead_score,
        "name": Customer.name,
    }

    async def get_by_normalized_phone(self, normalized_phone: str) -> Customer | None:
        stmt = self.base_query().where(Customer.normalized_phone == normalized_phone)
        return (await self.session.execute(stmt)).scalars().first()

    async def find_by_name_fuzzy(self, name: str, limit: int = 5) -> list[Customer]:
        """Used when no phone number is available - never auto-merges, only suggests."""
        pattern = f"%{name.strip().lower()}%"
        stmt = (
            self.base_query()
            .where(Customer.name.is_not(None))
            .where(Customer.name.ilike(pattern))
            .order_by(Customer.last_interaction_at.desc().nullslast())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    def build_list_query(
        self, filters: CustomerListFilters, *, restrict_to_user_id: uuid.UUID | None = None
    ) -> Select[tuple[Customer]]:
        stmt = self.base_query()
        if restrict_to_user_id is not None:
            stmt = stmt.where(Customer.owner_user_id == restrict_to_user_id)
        if filters.search:
            pattern = f"%{filters.search.lower()}%"
            stmt = stmt.where(
                or_(
                    Customer.name.ilike(pattern),
                    Customer.company.ilike(pattern),
                    Customer.requirement.ilike(pattern),
                    Customer.normalized_phone.ilike(f"%{filters.search.strip()}%"),
                )
            )
        if filters.lead_status:
            stmt = stmt.where(Customer.lead_status == filters.lead_status)
        if filters.purchase_intent:
            stmt = stmt.where(Customer.purchase_intent == filters.purchase_intent)
        if filters.min_budget is not None:
            stmt = stmt.where(Customer.budget_max >= filters.min_budget)
        if filters.max_budget is not None:
            stmt = stmt.where(Customer.budget_min <= filters.max_budget)
        if filters.location:
            stmt = stmt.where(Customer.location.ilike(f"%{filters.location}%"))
        if filters.owner_user_id:
            stmt = stmt.where(Customer.owner_user_id == filters.owner_user_id)
        if filters.updated_after:
            stmt = stmt.where(Customer.updated_at >= filters.updated_after)
        if filters.has_pending_follow_up is True:
            stmt = stmt.where(Customer.next_follow_up_at.is_not(None))
        elif filters.has_pending_follow_up is False:
            stmt = stmt.where(Customer.next_follow_up_at.is_(None))
        return stmt

    async def list_customers(
        self,
        filters: CustomerListFilters,
        params: PageParams,
        *,
        restrict_to_user_id: uuid.UUID | None = None,
    ) -> tuple[list[Customer], int]:
        stmt = self.build_list_query(filters, restrict_to_user_id=restrict_to_user_id)
        stmt = self.apply_sort(stmt, params, self.SORTABLE)
        return await self.paginate(stmt, params)

    async def count_by_status(self, since: datetime | None = None) -> dict[str, int]:
        stmt = select(Customer.lead_status, func.count()).where(
            Customer.business_id == self.business_id
        )
        if since is not None:
            stmt = stmt.where(Customer.created_at >= since)
        rows = (await self.session.execute(stmt.group_by(Customer.lead_status))).all()
        return {str(status): int(count) for status, count in rows}

    async def hot_leads_without_recent_contact(self, cutoff: datetime) -> list[Customer]:
        stmt = (
            self.base_query()
            .where(Customer.lead_status.in_([LeadStatus.HOT, LeadStatus.INTERESTED]))
            .where(
                or_(
                    Customer.last_interaction_at.is_(None),
                    Customer.last_interaction_at < cutoff,
                )
            )
            .where(Customer.next_follow_up_at.is_(None))
            .order_by(Customer.lead_score.desc())
            .limit(25)
        )
        return list((await self.session.execute(stmt)).scalars().all())
