from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BusinessVertical, Role


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en-IN", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Bumped on password change / logout-all so older refresh tokens stop working.
    token_version: Mapped[int] = mapped_column(default=0, nullable=False)

    memberships: Mapped[list[BusinessMembership]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class Business(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    vertical: Mapped[BusinessVertical] = mapped_column(
        String(32), default=BusinessVertical.GENERIC, nullable=False
    )
    country_code: Mapped[str] = mapped_column(String(2), default="IN", nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list[BusinessMembership]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )


class BusinessMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_memberships"
    __table_args__ = (
        UniqueConstraint("business_id", "user_id", name="uq_membership_business_user"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[Role] = mapped_column(String(24), default=Role.SALESPERSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="memberships", lazy="joined")
    business: Mapped[Business] = relationship(back_populates="memberships", lazy="joined")
