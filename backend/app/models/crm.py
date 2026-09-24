from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, JSONBCompat, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConversationSource, LeadStatus, PurchaseIntent, Sentiment


class Customer(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Customer identity = (business_id, normalized_phone).

    The unique constraint guarantees no duplicates inside a tenant while still
    allowing the *same* phone number to exist in other businesses, fully isolated.
    """

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("business_id", "normalized_phone", name="uq_customer_business_phone"),
        Index("ix_customers_business_updated", "business_id", "updated_at"),
        Index("ix_customers_business_followup", "business_id", "next_follow_up_at"),
        Index("ix_customers_business_name", "business_id", "name"),
    )

    name: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(32))
    normalized_phone: Mapped[str | None] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    company: Mapped[str | None] = mapped_column(String(160))
    location: Mapped[str | None] = mapped_column(String(160))

    requirement: Mapped[str | None] = mapped_column(Text)
    product: Mapped[str | None] = mapped_column(String(160))
    service: Mapped[str | None] = mapped_column(String(160))
    quantity: Mapped[str | None] = mapped_column(String(64))
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    timeline: Mapped[str | None] = mapped_column(String(160))
    availability: Mapped[str | None] = mapped_column(String(255))
    price_discussion: Mapped[str | None] = mapped_column(Text)

    purchase_intent: Mapped[PurchaseIntent] = mapped_column(
        String(16), default=PurchaseIntent.UNKNOWN, nullable=False
    )
    lead_status: Mapped[LeadStatus] = mapped_column(
        String(24), default=LeadStatus.NEW, nullable=False, index=True
    )
    lead_score: Mapped[int] = mapped_column(default=0, nullable=False)
    sentiment: Mapped[Sentiment] = mapped_column(
        String(16), default=Sentiment.UNKNOWN, nullable=False
    )
    pain_points: Mapped[list | None] = mapped_column(JSONBCompat)
    objections: Mapped[list | None] = mapped_column(JSONBCompat)
    competitors: Mapped[list | None] = mapped_column(JSONBCompat)
    decision_maker: Mapped[str | None] = mapped_column(String(160))

    query: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    source: Mapped[ConversationSource] = mapped_column(
        String(32), default=ConversationSource.MANUAL, nullable=False
    )

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Per-field confidence of the currently stored value. Used to stop a
    # low-confidence extraction from clobbering a high-confidence value.
    field_confidence: Mapped[dict] = mapped_column(JSONBCompat, default=dict, nullable=False)

    lead: Mapped[Lead | None] = relationship(
        back_populates="customer", uselist=False, cascade="all, delete-orphan"
    )


class Lead(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("business_id", "customer_id", name="uq_lead_business_customer"),
        Index("ix_leads_business_status", "business_id", "status"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[LeadStatus] = mapped_column(
        String(24), default=LeadStatus.NEW, nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(default=0, nullable=False)
    source: Mapped[ConversationSource] = mapped_column(
        String(32), default=ConversationSource.MANUAL, nullable=False
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lost_reason: Mapped[str | None] = mapped_column(String(255))

    customer: Mapped[Customer] = relationship(back_populates="lead", lazy="joined")
    transitions: Mapped[list[LeadStatusTransition]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class LeadStatusTransition(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "lead_status_transitions"
    __table_args__ = (Index("ix_lst_business_created", "business_id", "created_at"),)

    lead_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_status: Mapped[LeadStatus | None] = mapped_column(String(24))
    to_status: Mapped[LeadStatus] = mapped_column(String(24), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(String(255))

    lead: Mapped[Lead] = relationship(back_populates="transitions")


class ConversionEvent(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "conversion_events"
    __table_args__ = (Index("ix_conversion_business_created", "business_id", "created_at"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("leads.id", ondelete="SET NULL")
    )
    value_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    converted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
