"""Organizations, teams and membership - the spine of BaatX multi-tenancy.

A ``Business`` is the tenant. Every CRM row already carries ``business_id`` via
``TenantMixin``; this module adds the *structure inside* a tenant - teams, a
manager/lead/member hierarchy, and the memberships that decide who sees what.

Two rules this file exists to enforce:

1. A user reaches CRM data only through a ``BusinessMembership``. No membership,
   no access - there is no other door.
2. Role and team live on the membership, not on the user. The same person can
   be a manager in one organization and a salesperson in another.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, JSONBCompat, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BusinessVertical, OrgRole


class Business(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An organization. The tenant boundary - nothing crosses it."""

    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    vertical: Mapped[BusinessVertical] = mapped_column(
        String(32), default=BusinessVertical.GENERIC, nullable=False
    )
    country_code: Mapped[str] = mapped_column(String(2), default="IN", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list[BusinessMembership]] = relationship(
        back_populates="business", cascade="all, delete-orphan", lazy="selectin"
    )
    teams: Mapped[list[Team]] = relationship(
        back_populates="business", cascade="all, delete-orphan", lazy="selectin"
    )


class Team(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A team inside one organization, e.g. "North Delhi Sales"."""

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_team_business_name"),
        Index("ix_teams_business", "business_id"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))

    # Denormalised for fast "who leads this team?" lookups. The authoritative
    # source is still the membership row with role=TEAM_LEAD.
    lead_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # Optional nesting for organizations that run sub-teams. Visibility walks
    # this tree downward: a lead sees their team and everything under it.
    parent_team_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped[Business] = relationship(back_populates="teams")
    memberships: Mapped[list[BusinessMembership]] = relationship(
        back_populates="team", lazy="selectin"
    )


class BusinessMembership(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """One user's place in one organization: role, team and permissions.

    This is the only thing that grants access to a tenant. Deactivating the row
    revokes everything, immediately and everywhere.
    """

    __tablename__ = "business_memberships"
    __table_args__ = (
        UniqueConstraint("business_id", "user_id", name="uq_membership_business_user"),
        Index("ix_memberships_user", "user_id"),
        Index("ix_memberships_business_team", "business_id", "team_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[OrgRole] = mapped_column(String(24), default=OrgRole.MEMBER, nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("teams.id", ondelete="SET NULL")
    )

    # Free-text label shown in the UI: "Salesperson", "Broker", "Agent".
    # Purely cosmetic - it never affects authorization.
    job_title: Mapped[str | None] = mapped_column(String(80))

    # Per-user overrides on top of the role's defaults. Grants are additive;
    # revocations win. Empty means "just use the role".
    granted_permissions: Mapped[list | None] = mapped_column(JSONBCompat)
    revoked_permissions: Mapped[list | None] = mapped_column(JSONBCompat)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    business: Mapped[Business] = relationship(back_populates="memberships")
    team: Mapped[Team | None] = relationship(back_populates="memberships")


class Invitation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A pending invite to join an organization."""

    __tablename__ = "invitations"
    __table_args__ = (
        Index("ix_invitations_business_status", "business_id", "status"),
        Index("ix_invitations_token", "token", unique=True),
    )

    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)

    role: Mapped[OrgRole] = mapped_column(String(24), default=OrgRole.MEMBER, nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("teams.id", ondelete="SET NULL")
    )
    job_title: Mapped[str | None] = mapped_column(String(80))

    # Random and single-use.
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
