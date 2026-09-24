from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.followup import Notification
from app.repositories.base import TenantRepository


class NotificationRepository(TenantRepository[Notification]):
    model = Notification

    async def exists_dedupe(self, dedupe_key: str) -> bool:
        stmt = select(Notification.id).where(
            Notification.business_id == self.business_id,
            Notification.dedupe_key == dedupe_key,
        )
        return (await self.session.execute(stmt)).first() is not None

    async def for_user(self, user_id: uuid.UUID, limit: int = 50) -> list[Notification]:
        stmt = (
            self.base_query()
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())
