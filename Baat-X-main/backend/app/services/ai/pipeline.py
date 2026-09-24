"""The BaatX pipeline: audio/text -> transcript -> extraction -> reviewed CRM update.

Split into two halves on purpose:

  ``AIProcessingService.process_job``  runs in the background worker. It is
  idempotent, retry-safe, and deletes the temporary audio as soon as the
  transcript exists.

  ``AIProcessingService.apply_extraction`` runs in the API request after the
  user taps "Save to CRM" on the review screen. Nothing touches the CRM before
  that tap.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.core.errors import AIProcessingError, ConflictError, NotFoundError, ValidationError
from app.core.phone import normalize_phone
from app.models.conversation import AIExtraction, AIProcessingJob, ConversationEvent
from app.models.enums import (
    BusinessVertical,
    ConversationSource,
    JobStage,
    JobStatus,
    LeadStatus,
    PurchaseIntent,
    QueryCategory,
    Sentiment,
)
from app.models.tenancy import Business
from app.repositories.job_repo import ExtractionRepository, JobRepository
from app.repositories.report_repo import ReportRepository
from app.schemas.ai import (
    ApplyExtractionRequest,
    ApplyExtractionResponse,
    ExtractionPayload,
    ExtractionReviewResponse,
    ReviewItem,
    confidence_band,
)
from app.schemas.followup import FollowUpCreate
from app.services.ai.base import LLMProvider, SpeechToTextProvider, StorageProvider
from app.services.ai.extraction import ExtractionService, needs_confirmation_fields
from app.services.crm.customer_service import CustomerService
from app.services.crm.merge import customer_context_hint, merge_extraction_into_customer
from app.services.reminders.followup_service import (
    FOLLOW_UP_TITLES,
    FollowUpService,
    infer_status_from_followup,
)

log = get_logger(__name__)

REVIEW_LABELS: list[tuple[str, str]] = [
    ("customer_name", "Customer"),
    ("phone_number", "Phone"),
    ("requirement", "Requirement"),
    ("product", "Product"),
    ("budget", "Budget"),
    ("location", "Location"),
    ("customer_query", "Query"),
    ("purchase_intent", "Intent"),
    ("lead_status", "Status"),
    ("timeline", "Timeline"),
    ("availability", "Availability"),
    ("competitors", "Competitors"),
    ("objections", "Objections"),
]


class AIProcessingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        business_id: uuid.UUID,
        llm: LLMProvider,
        stt: SpeechToTextProvider,
        storage: StorageProvider,
        settings: Settings | None = None,
        timezone: str = "Asia/Kolkata",
        country_code: str = "IN",
    ) -> None:
        self.session = session
        self.business_id = business_id
        self.settings = settings or get_settings()
        self.timezone = timezone
        self.country_code = country_code
        self.storage = storage
        self.stt = stt
        self.llm = llm
        self.jobs = JobRepository(session, business_id)
        self.extractions = ExtractionRepository(session, business_id)
        self.reports = ReportRepository(session, business_id)
        self.extractor = ExtractionService(llm, self.settings)
        self.customers = CustomerService(session, business_id, country_code)
        self.follow_ups = FollowUpService(session, business_id, timezone)

    # ---------------- job intake ----------------

    async def create_job(
        self,
        *,
        source: ConversationSource,
        idempotency_key: str,
        user_id: uuid.UUID | None,
        audio_blob_name: str | None = None,
        audio_mime_type: str | None = None,
        audio_size_bytes: int | None = None,
        transcript_text: str | None = None,
        hinted_customer_id: uuid.UUID | None = None,
        hinted_phone: str | None = None,
        hinted_name: str | None = None,
    ) -> tuple[AIProcessingJob, bool]:
        """Create (or return) a job. Replays of the same key never double-process."""
        existing = await self.jobs.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing, False

        job = AIProcessingJob(
            business_id=self.business_id,
            created_by_user_id=user_id,
            idempotency_key=idempotency_key,
            source=source,
            status=JobStatus.QUEUED,
            stage_label=(JobStage.UPLOADING if audio_blob_name else JobStage.UNDERSTANDING).value,
            progress=5,
            audio_blob_name=audio_blob_name,
            audio_mime_type=audio_mime_type,
            audio_size_bytes=audio_size_bytes,
            hinted_customer_id=hinted_customer_id,
            hinted_phone=normalize_phone(hinted_phone, self.country_code) if hinted_phone else None,
            hinted_name=(hinted_name or "").strip()[:160] or None,
        )
        self.session.add(job)
        await self.session.flush()

        if transcript_text:
            # Tell AI text is carried on the extraction row only until the worker consumes it.
            self.session.add(
                AIExtraction(
                    business_id=self.business_id,
                    job_id=job.id,
                    payload={"_pending_text": transcript_text[:20_000]},
                    overall_confidence=0.0,
                )
            )
            await self.session.flush()

        return job, True

    async def _set_stage(
        self, job: AIProcessingJob, status: JobStatus, stage: JobStage, progress: int
    ) -> None:
        job.status = status
        job.stage_label = stage.value
        job.progress = max(job.progress, min(progress, 100))
        await self.session.flush()

    # ---------------- worker half ----------------

    async def process_job(self, job_id: uuid.UUID) -> AIExtraction:
        job = await self.jobs.get(job_id)
        if job is None:
            raise NotFoundError("job not found")

        if job.status in (JobStatus.AWAITING_REVIEW, JobStatus.APPLIED):
            extraction = await self.extractions.get_by_job(job.id)
            if extraction is not None:
                return extraction  # idempotent replay

        job.attempts += 1
        job.started_at = job.started_at or datetime.now(UTC)
        await self.session.flush()

        try:
            transcript = await self._obtain_transcript(job)
            await self._set_stage(job, JobStatus.ANALYZING, JobStage.EXTRACTING_CUSTOMER, 55)

            hint = None
            if job.hinted_customer_id:
                customer = await self.customers.customers.get(job.hinted_customer_id)
                hint = customer_context_hint(customer)
            elif job.hinted_phone:
                # A call we already know the number for: pull the existing CRM
                # record so the model can disambiguate, never to fill blanks.
                known = await self.customers.customers.get_by_normalized_phone(job.hinted_phone)
                hint = customer_context_hint(known)

            business = await self.session.get(Business, self.business_id)
            payload = await self.extractor.extract(
                transcript,
                vertical=(
                    BusinessVertical(business.vertical) if business else BusinessVertical.GENERIC
                ),
                currency=business.default_currency if business else "INR",
                known_customer_hint=hint,
                timezone=self.timezone,
            )

            await self._set_stage(job, JobStatus.EXTRACTING, JobStage.FINDING_FOLLOWUPS, 75)
            matched_customer = await self._match_customer(job, payload)

            await self._set_stage(job, JobStatus.EXTRACTING, JobStage.PREPARING_UPDATE, 90)

            extraction = await self.extractions.get_by_job(job.id)
            if extraction is None:
                extraction = AIExtraction(
                    business_id=self.business_id, job_id=job.id, payload={}, overall_confidence=0.0
                )
                self.session.add(extraction)

            extraction.payload = payload.model_dump(mode="json")
            extraction.overall_confidence = payload.overall_confidence()
            extraction.needs_confirmation = needs_confirmation_fields(
                payload, self.settings.confidence_medium
            )
            extraction.customer_id = matched_customer.id if matched_customer else None
            extraction.model_name = getattr(self.llm, "model", None)
            extraction.stt_provider = getattr(self.stt, "name", None)
            extraction.transcript = transcript if self.settings.retain_transcripts else None

            job.language_detected = payload.language_detected
            job.status = JobStatus.AWAITING_REVIEW
            job.stage_label = JobStage.DONE.value
            job.progress = 100
            job.finished_at = datetime.now(UTC)
            await self.session.flush()

            log.info(
                "job_processed",
                job_id=str(job.id),
                confidence=extraction.overall_confidence,
                matched_existing=bool(matched_customer),
            )
            return extraction

        except Exception as exc:  # noqa: BLE001 - recorded, then re-raised for the queue
            job.status = JobStatus.FAILED
            job.error_code = getattr(exc, "code", "internal_error")
            job.error_message = getattr(exc, "user_message", None) or (
                "Something went wrong while processing your recording. Please try again."
            )
            job.finished_at = datetime.now(UTC)
            await self.session.flush()
            log.warning("job_failed", job_id=str(job.id), error=type(exc).__name__)
            raise
        finally:
            # Temporary audio never outlives processing, success or failure.
            await self._delete_audio(job)

    async def _obtain_transcript(self, job: AIProcessingJob) -> str:
        pending = await self.extractions.get_by_job(job.id)
        if pending is not None and isinstance(pending.payload, dict):
            text = pending.payload.get("_pending_text")
            if text:
                await self._set_stage(job, JobStatus.ANALYZING, JobStage.UNDERSTANDING, 40)
                return str(text)

        if not job.audio_blob_name:
            raise AIProcessingError("job has neither text nor audio")

        await self._set_stage(job, JobStatus.TRANSCRIBING, JobStage.UNDERSTANDING, 25)
        audio = await self.storage.download(job.audio_blob_name)
        result = await self.stt.transcribe(
            audio_bytes=audio,
            content_type=job.audio_mime_type,
            candidate_locales=self.settings.stt_candidate_locales,
        )
        if result.duration_seconds:
            job.audio_duration_seconds = int(result.duration_seconds)
        job.language_detected = result.language
        if not result.text.strip():
            raise AIProcessingError(
                "empty transcript",
                user_message="We couldn't hear anything in that recording. Please try again.",
            )
        return result.text

    async def _delete_audio(self, job: AIProcessingJob) -> None:
        if not job.audio_blob_name or not self.settings.delete_audio_after_processing:
            return
        deleted = await self.storage.delete(job.audio_blob_name)
        if deleted:
            job.audio_blob_name = None
            job.audio_deleted_at = datetime.now(UTC)
            await self.session.flush()

    async def _match_customer(self, job: AIProcessingJob, payload: ExtractionPayload):  # noqa: ANN202
        if job.hinted_customer_id:
            return await self.customers.customers.get(job.hinted_customer_id)

        # The number the device attached wins over anything heard in the audio:
        # it is the number that was actually dialled/received.
        phone = job.hinted_phone or payload.phone_number.value
        if phone:
            normalized = normalize_phone(str(phone), self.country_code)
            if normalized:
                return await self.customers.customers.get_by_normalized_phone(normalized)
        return None

    # ---------------- review ----------------

    async def build_review(self, extraction: AIExtraction) -> ExtractionReviewResponse:
        payload = ExtractionPayload.model_validate(extraction.payload)
        items: list[ReviewItem] = []
        flagged = set(extraction.needs_confirmation or [])

        job = await self.jobs.get(extraction.job_id)

        for key, label in REVIEW_LABELS:
            field = getattr(payload, key, None)
            if field is None or field.value in (None, "", []):
                # Surface the contact details the device already knew, so the
                # review screen always shows who this call was with.
                if key == "phone_number" and job is not None and job.hinted_phone:
                    items.append(
                        ReviewItem(
                            key=key,
                            label=label,
                            value=job.hinted_phone,
                            confidence=1.0,
                            band=confidence_band(1.0),
                            needs_confirmation=False,
                            source_text="From the call you just finished",
                        )
                    )
                elif key == "customer_name" and job is not None and job.hinted_name:
                    items.append(
                        ReviewItem(
                            key=key,
                            label=label,
                            value=job.hinted_name,
                            confidence=1.0,
                            band=confidence_band(1.0),
                            needs_confirmation=False,
                            source_text="From your contacts",
                        )
                    )
                continue

            items.append(
                ReviewItem(
                    key=key,
                    label=label,
                    value=field.value,
                    confidence=field.confidence,
                    band=confidence_band(field.confidence),
                    needs_confirmation=key in flagged,
                    source_text=field.source_text,
                )
            )

        return ExtractionReviewResponse(
            extraction_id=extraction.id,
            job_id=extraction.job_id,
            customer_id=extraction.customer_id,
            matched_existing_customer=extraction.customer_id is not None,
            items=items,
            summary=payload.summary,
            follow_up=payload.follow_up,
            overall_confidence=extraction.overall_confidence,
            needs_confirmation=list(flagged),
            payload=payload,
        )

    # ---------------- apply (after human review) ----------------

    async def apply_extraction(
        self,
        extraction_id: uuid.UUID,
        request: ApplyExtractionRequest,
        *,
        actor_id: uuid.UUID | None,
    ) -> ApplyExtractionResponse:
        extraction = await self.extractions.get_or_404(extraction_id)
        if extraction.applied:
            raise ConflictError(
                "already applied", user_message="This conversation was already saved."
            )

        job = await self.jobs.get_or_404(extraction.job_id)
        payload = ExtractionPayload.model_validate(extraction.payload)

        # Identity order: what the user typed > the number actually dialled >
        # whatever was heard in the conversation.
        phone = (
            request.phone_override
            or job.hinted_phone
            or (str(payload.phone_number.value) if payload.phone_number.value else None)
        )
        name = (
            request.edited_fields.get("customer_name")
            or payload.customer_name.value
            or job.hinted_name
        )

        customer, matched, candidates = await self.customers.resolve_or_create(
            phone=phone,
            name=str(name) if name else None,
            customer_id=request.customer_id or extraction.customer_id,
            source=ConversationSource(job.source),
            owner_user_id=actor_id,
            create_if_missing=request.create_customer,
        )
        if customer is None:
            raise ValidationError(
                "customer required",
                user_message="Please choose an existing customer or add a phone number.",
                details={"candidates": [c.model_dump(mode="json") for c in candidates]},
            )

        merge = merge_extraction_into_customer(
            customer, payload, edited_fields=request.edited_fields
        )

        # A known contact name fills a blank, but never overwrites one we have.
        if job.hinted_name and not customer.name:
            customer.name = job.hinted_name

        # Enum-ish fields need explicit coercion before they hit the columns.
        if payload.purchase_intent.value:
            try:
                customer.purchase_intent = PurchaseIntent(str(payload.purchase_intent.value))
            except ValueError:
                pass
        if payload.sentiment.value:
            try:
                customer.sentiment = Sentiment(str(payload.sentiment.value))
            except ValueError:
                pass
        if payload.summary:
            customer.summary = payload.summary

        customer.last_interaction_at = datetime.now(UTC)
        customer.source = ConversationSource(job.source)

        # Lead status: explicit edit > AI value (if confident) > funnel inference.
        status_override = request.edited_fields.get("lead_status")
        new_status: LeadStatus | None = None
        if status_override:
            new_status = LeadStatus(str(status_override))
        elif (
            payload.lead_status.value
            and payload.lead_status.confidence >= self.settings.confidence_medium
        ):
            try:
                new_status = LeadStatus(str(payload.lead_status.value))
            except ValueError:
                new_status = None
        if new_status is None and payload.follow_up.required:
            new_status = infer_status_from_followup(LeadStatus(customer.lead_status))
        if new_status:
            await self.customers.set_lead_status(customer, new_status, actor_id=actor_id)

        event = await self._create_timeline_event(job, customer, payload, actor_id)

        follow_up_id: uuid.UUID | None = None
        if request.confirm_follow_up and payload.follow_up.required:
            due_at = request.follow_up_due_at or payload.follow_up.resolved_due_at
            # No resolvable date means no follow-up - BaatX never invents one.
            if due_at is not None:
                follow_up_type = request.follow_up_type or payload.follow_up.type
                created = await self.follow_ups.create(
                    FollowUpCreate(
                        customer_id=customer.id,
                        type=follow_up_type,
                        title=payload.follow_up.action
                        or FOLLOW_UP_TITLES.get(follow_up_type, "Follow-up"),
                        due_at=due_at,
                        due_time_known=payload.follow_up.resolved_time_known
                        or request.follow_up_due_at is not None,
                        reason=payload.follow_up.reason,
                        customer_requested_callback=payload.follow_up.customer_requested_callback,
                    ),
                    actor_id=actor_id,
                    created_by_ai=True,
                    confidence=payload.follow_up.confidence,
                )
                follow_up_id = created.id

        extraction.applied = True
        extraction.reviewed_at = datetime.now(UTC)
        extraction.reviewed_by_user_id = actor_id
        extraction.customer_id = customer.id
        job.status = JobStatus.APPLIED
        await self.session.flush()

        log.info(
            "extraction_applied",
            job_id=str(job.id),
            matched_existing=matched,
            updated=len(merge.updated_fields),
            skipped=len(merge.skipped_low_confidence),
        )

        return ApplyExtractionResponse(
            customer_id=customer.id,
            conversation_event_id=event.id,
            follow_up_id=follow_up_id,
            lead_status=LeadStatus(customer.lead_status),
            updated_fields=merge.updated_fields,
            skipped_low_confidence_fields=merge.skipped_low_confidence,
        )

    async def _create_timeline_event(
        self,
        job: AIProcessingJob,
        customer,  # noqa: ANN001
        payload: ExtractionPayload,
        actor_id: uuid.UUID | None,
    ) -> ConversationEvent:
        categories = [QueryCategory(str(c)) for c in (payload.query_categories.value or [])]
        highlights: dict[str, Any] = {
            key: getattr(payload, key).value
            for key in (
                "requirement", "budget", "location", "customer_query",
                "purchase_intent", "product", "timeline",
            )
            if getattr(payload, key).value not in (None, "", [])
        }
        if payload.follow_up.required and payload.follow_up.action:
            highlights["next_action"] = payload.follow_up.action

        source = ConversationSource(job.source)
        title = (
            "Call Recording"
            if source == ConversationSource.IMPORT_CALL_RECORDING
            else "Customer Conversation"
        )

        event = ConversationEvent(
            business_id=self.business_id,
            customer_id=customer.id,
            job_id=job.id,
            created_by_user_id=actor_id,
            source=source,
            occurred_at=datetime.now(UTC),
            title=title,
            summary=payload.summary,
            highlights=highlights,
            query_text=str(payload.customer_query.value) if payload.customer_query.value else None,
            query_categories=[c.value for c in categories],
            primary_query_category=categories[0] if categories else None,
            duration_seconds=job.audio_duration_seconds,
        )
        self.session.add(event)
        await self.session.flush()

        today = event.occurred_at.date()
        for category in categories:
            await self.reports.bump_query_category(today, category)
        return event
