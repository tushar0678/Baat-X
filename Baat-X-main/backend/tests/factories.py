"""Test data factories."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.models import Business, BusinessMembership, User
from app.models.enums import BusinessVertical, Role


async def make_business(
    session: AsyncSession,
    *,
    name: str = "Sharma Properties",
    vertical: BusinessVertical = BusinessVertical.REAL_ESTATE,
    owner_email: str | None = None,
) -> tuple[Business, User]:
    business = Business(name=name, vertical=vertical, timezone="Asia/Kolkata")
    user = User(
        email=owner_email or f"{uuid.uuid4().hex[:8]}@example.com",
        full_name="Owner",
        password_hash=hash_password("StrongPassw0rd!"),
    )
    session.add_all([business, user])
    await session.flush()
    session.add(BusinessMembership(business_id=business.id, user_id=user.id, role=Role.OWNER))
    await session.flush()
    return business, user
