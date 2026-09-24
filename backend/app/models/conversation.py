from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, JSONBCompat, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConversationSource, JobStatus, QueryCategory


class AIProcessingJob(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """One row per audio/text submission. Drives the progress UI on Android."""

    __tablename__ = "ai_processing_jobs"
    __table_args__ = (
        UniqueConstraint("business_id", "idempotency_key", name="uq_job_business_idem"),
        Index("ix_jobs_business_status", "business_id", "status"),
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[ConversationSource] = mapped_column(String(32), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        String(24), default=JobStatus.QUEUED, nullable=False, index=True
    )
    stage_label: Mapped[str] = mapped_column(
        String(80), default="Uploading audio...", nullable=False
    )
    progress: Mapped[int] = mapped_column(default=0, nullable=False)

    # Storage pointer only - never the audio bytes, and cleared on deletion.
    audio_blob_name: Mapped[str | None] = mapped_column(String(512))
    audio_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_mime_type: Mapped[str | None] = mapped_column(String(80))
    audio_size_bytes: Mapped[int | None] = mapped_column()
    audio_duration_seconds: Mapped[int | None] = mapped_column()
    language_detected: Mapped[str | None] = mapped_column(String(16))

    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    hinted_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="SET NULL")
    )
    hinted_phone: Mapped[str | None] = mapped_column(String(32))
    # Contact name the device already knew (e.g. from the call the user just
    # finished). Used only as a fallback when the conversation itself never
    # says the name - it is never invented and never overrides a spoken name.
    hinted_name: Mapped[str | None] = mapped_column(String(160))

    extraction: Mapped[AIExtraction | None] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )


class AIExtraction(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Structured, per-field AI output awaiting (or after) human review."""

    __tablename__ = "ai_extractions"
    __table_args__ = (Index("ix_extractions_business_created", "business_id", "created_at"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("ai_processing_jobs.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    payload: Mapped[dict] = mapped_column(JSONBCompat, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    needs_confirmation: Mapped[list | None] = mapped_column(JSONBCompat)
    model_name: Mapped[str | None] = mapped_column(String(80))
    stt_provider: Mapped[str | None] = mapped_column(String(40))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Retained only when Settings.retain_transcripts is explicitly enabled.
    transcript: Mapped[str | None] = mapped_column(Text)

    job: Mapped[AIProcessingJob] = relationship(back_populates="extraction")


class ConversationEvent(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A timeline entry: structured business facts, never audio."""

    __tablename__ = "conversation_events"
    __table_args__ = (
        Index("ix_events_business_customer_created", "business_id", "customer_id", "created_at"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("ai_processing_jobs.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    source: Mapped[ConversationSource] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String(160), default="Customer Conversation", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    highlights: Mapped[dict | None] = mapped_column(JSONBCompat)
    query_text: Mapped[str | None] = mapped_column(Text)
    query_categories: Mapped[list | None] = mapped_column(JSONBCompat)
    primary_query_category: Mapped[QueryCategory | None] = mapped_column(String(32), index=True)
    duration_seconds: Mapped[int | None] = mapped_column()
