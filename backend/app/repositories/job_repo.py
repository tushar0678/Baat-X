from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.conversation import AIExtraction, AIProcessingJob, ConversationEvent
from app.repositories.base import TenantRepository


class JobRepository(TenantRepository[AIProcessingJob]):
    model = AIProcessingJob

    async def get_by_idempotency_key(self, key: str) -> AIProcessingJob | None:
        stmt = self.base_query().where(AIProcessingJob.idempotency_key == key)
        return (await self.session.execute(stmt)).scalars().first()

    async def recent(self, limit: int = 20) -> list[AIProcessingJob]:
        stmt = self.base_query().order_by(AIProcessingJob.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())


class ExtractionRepository(TenantRepository[AIExtraction]):
    model = AIExtraction

    async def get_by_job(self, job_id: uuid.UUID) -> AIExtraction | None:
        stmt = self.base_query().where(AIExtraction.job_id == job_id)
        return (await self.session.execute(stmt)).scalars().first()


class ConversationEventRepository(TenantRepository[ConversationEvent]):
    model = ConversationEvent

    async def for_customer(
        self, customer_id: uuid.UUID, limit: int = 100
    ) -> list[ConversationEvent]:
        stmt = (
            self.base_query()
            .where(ConversationEvent.customer_id == customer_id)
            .order_by(ConversationEvent.occurred_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def between(self, start, end, limit: int = 1000):  # noqa: ANN001, ANN201
        stmt = (
            self.base_query()
            .where(ConversationEvent.occurred_at >= start)
            .where(ConversationEvent.occurred_at < end)
            .order_by(ConversationEvent.occurred_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def distinct_customers_contacted(self, start, end) -> int:  # noqa: ANN001
        stmt = (
            select(func.count(func.distinct(ConversationEvent.customer_id)))
            .where(ConversationEvent.business_id == self.business_id)
            .where(ConversationEvent.occurred_at >= start)
            .where(ConversationEvent.occurred_at < end)
        )
        return int((await self.session.execute(stmt)).scalar_one())
