from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging import get_logger
from app.models.enums import NotificationType
from app.models.followup import Notification
from app.repositories.notification_repo import NotificationRepository

log = get_logger(__name__)


class NotificationService:
    """In-app notification store.

    `dedupe_key` is unique per tenant, which is what keeps BaatX from spamming a
    salesperson with the same reminder every sweep (§17).
    """

    def __init__(self, session: AsyncSession, business_id: uuid.UUID) -> None:
        self.session = session
        self.business_id = business_id
        self.repo = NotificationRepository(session, business_id)

    async def create(
        self,
        *,
        user_id: uuid.UUID | None,
        type: NotificationType,  # noqa: A002 - mirrors the column name
        title: str,
        body: str,
        dedupe_key: str,
        customer_id: uuid.UUID | None = None,
        follow_up_id: uuid.UUID | None = None,
        data: dict | None = None,
    ) -> Notification | None:
        if await self.repo.exists_dedupe(dedupe_key):
            return None
        notification = Notification(
            business_id=self.business_id,
            user_id=user_id,
            customer_id=customer_id,
            follow_up_id=follow_up_id,
            type=type,
            title=title[:160],
            body=body[:500],
            data=data,
            dedupe_key=dedupe_key[:160],
        )
        self.session.add(notification)
        try:
            await self.session.flush()
        except IntegrityError:
            # Lost a race with a concurrent sweep - the notification already exists.
            await self.session.rollback()
            return None
        return notification

    async def list_for_user(self, user_id: uuid.UUID, limit: int = 50) -> list[Notification]:
        return await self.repo.for_user(user_id, limit)

    async def mark_read(self, notification_id: uuid.UUID) -> Notification:
        from datetime import UTC, datetime

        notification = await self.repo.get_or_404(notification_id)
        notification.read_at = datetime.now(UTC)
        return notification
