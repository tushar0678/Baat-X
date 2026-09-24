from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from app.auth.deps import CurrentUser, DbDep, requires
from app.config.settings import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.models.enums import ConversationSource, JobStatus
from app.repositories.audit_repo import AuditRepository
from app.schemas.ai import (
    ApplyExtractionRequest,
    ApplyExtractionResponse,
    ExtractionReviewResponse,
    JobStatusResponse,
    ProcessAudioResponse,
    TellAIRequest,
)
from app.services.ai.factory import llm_provider, storage_provider, stt_provider
from app.services.ai.pipeline import AIProcessingService
from app.services.audio.validator import validate_audio
from app.workers.queue import enqueue_job

router = APIRouter(prefix="/ai", tags=["AI"])


def _service(db, principal: CurrentUser) -> AIProcessingService:  # noqa: ANN001
    return AIProcessingService(
        db,
        business_id=principal.business_id,
        llm=llm_provider(),
        stt=stt_provider(),
        storage=storage_provider(),
        timezone=principal.business.timezone,
        country_code=principal.business.country_code,
    )


@router.post(
    "/process-audio",
    response_model=ProcessAudioResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a call recording or audio file for processing",
)
async def process_audio(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("ai:process")],
    file: Annotated[UploadFile, File(description="MP3, M4A, WAV, AAC, AMR or OGG")],
    idempotency_key: Annotated[str, Form(min_length=8, max_length=80)],
    source: Annotated[ConversationSource, Form()] = ConversationSource.IMPORT_AUDIO,
    customer_id: Annotated[uuid.UUID | None, Form()] = None,
    phone_hint: Annotated[str | None, Form(max_length=32)] = None,
    name_hint: Annotated[str | None, Form(max_length=160)] = None,
) -> ProcessAudioResponse:
    """Audio is stored privately with a short TTL and deleted right after processing.

    ``phone_hint``/``name_hint`` let the client attach the contact it already
    knows - for example the call the user just finished. The phone number is
    what links this conversation to an existing customer, so the next call from
    the same number lands on the same CRM record.
    """
    settings = get_settings()
    service = _service(db, principal)

    existing = await service.jobs.get_by_idempotency_key(idempotency_key)
    if existing is not None:
        return ProcessAudioResponse(
            job_id=existing.id,
            status=JobStatus(existing.status),
            stage_label=existing.stage_label,
            progress=existing.progress,
        )

    data = await file.read(settings.audio_max_bytes + 1)
    audio = validate_audio(
        filename=file.filename,
        declared_content_type=file.content_type,
        data=data,
        settings=settings,
    )

    blob_name = (
        f"{principal.business_id}/{datetime.now(UTC):%Y/%m/%d}/"
        f"{uuid.uuid4().hex}.{audio.extension}"
    )
    await storage_provider().upload(
        blob_name=blob_name,
        data=data,
        content_type=audio.content_type,
        ttl_minutes=settings.audio_temp_ttl_minutes,
    )

    job, _ = await service.create_job(
        source=source,
        idempotency_key=idempotency_key,
        user_id=principal.user_id,
        audio_blob_name=blob_name,
        audio_mime_type=audio.content_type,
        audio_size_bytes=audio.size_bytes,
        hinted_customer_id=customer_id,
        hinted_phone=phone_hint,
        hinted_name=name_hint,
    )

    await AuditRepository(db, principal.business_id).record(
        action="ai.audio_submitted",
        actor_user_id=principal.user_id,
        entity_type="ai_processing_job",
        entity_id=job.id,
        request_id=getattr(request.state, "request_id", None),
        # Identifiers and outcomes only - never the number or the name itself.
        metadata={
            "source": source.value,
            "size_bytes": audio.size_bytes,
            "has_phone_hint": phone_hint is not None,
        },
    )
    await db.commit()

    await enqueue_job(job.id, principal.business_id)
    return ProcessAudioResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        stage_label=job.stage_label,
        progress=job.progress,
    )


@router.post(
    "/tell-ai",
    response_model=ProcessAudioResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a spoken/typed note about a customer conversation",
)
async def tell_ai(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("ai:process")],
    payload: TellAIRequest,
) -> ProcessAudioResponse:
    service = _service(db, principal)
    job, created = await service.create_job(
        source=payload.source,
        idempotency_key=payload.idempotency_key,
        user_id=principal.user_id,
        transcript_text=payload.text,
        hinted_customer_id=payload.customer_id,
        hinted_phone=payload.phone_hint,
    )
    if created:
        await AuditRepository(db, principal.business_id).record(
            action="ai.tell_ai_submitted",
            actor_user_id=principal.user_id,
            entity_type="ai_processing_job",
            entity_id=job.id,
            request_id=getattr(request.state, "request_id", None),
        )
    await db.commit()
    if created:
        await enqueue_job(job.id, principal.business_id)
    return ProcessAudioResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        stage_label=job.stage_label,
        progress=job.progress,
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse, summary="Poll processing progress")
async def job_status(
    db: DbDep, principal: Annotated[CurrentUser, requires("ai:process")], job_id: uuid.UUID
) -> JobStatusResponse:
    service = _service(db, principal)
    job = await service.jobs.get_or_404(job_id)
    extraction = await service.extractions.get_by_job(job.id)
    has_result = extraction is not None and not (
        isinstance(extraction.payload, dict) and "_pending_text" in extraction.payload
    )
    return JobStatusResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        stage_label=job.stage_label,
        progress=job.progress,
        error_code=job.error_code,
        error_message=job.error_message,
        extraction_id=extraction.id if has_result else None,
        customer_id=extraction.customer_id if has_result else None,
    )


@router.get(
    "/jobs/{job_id}/review",
    response_model=ExtractionReviewResponse,
    summary="Here's what I understood",
)
async def review(
    db: DbDep, principal: Annotated[CurrentUser, requires("ai:process")], job_id: uuid.UUID
) -> ExtractionReviewResponse:
    service = _service(db, principal)
    job = await service.jobs.get_or_404(job_id)
    extraction = await service.extractions.get_by_job(job.id)
    if extraction is None or (
        isinstance(extraction.payload, dict) and "_pending_text" in extraction.payload
    ):
        raise NotFoundError(
            "extraction not ready",
            user_message="We're still working on this conversation. Please wait a moment.",
        )
    return await service.build_review(extraction)


@router.post(
    "/extractions/{extraction_id}/apply",
    response_model=ApplyExtractionResponse,
    summary="Save the reviewed extraction to the CRM",
)
async def apply_extraction(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:write")],
    extraction_id: uuid.UUID,
    payload: ApplyExtractionRequest,
) -> ApplyExtractionResponse:
    service = _service(db, principal)

    if payload.discard:
        extraction = await service.extractions.get_or_404(extraction_id)
        if extraction.applied:
            raise ConflictError("already applied")
        await service.extractions.delete(extraction)
        await db.commit()
        raise NotFoundError("discarded", user_message="This conversation was discarded.")

    result = await service.apply_extraction(extraction_id, payload, actor_id=principal.user_id)
    await AuditRepository(db, principal.business_id).record(
        action="crm.extraction_applied",
        actor_user_id=principal.user_id,
        entity_type="customer",
        entity_id=result.customer_id,
        request_id=getattr(request.state, "request_id", None),
        metadata={
            "updated_fields": result.updated_fields,
            "skipped_low_confidence": result.skipped_low_confidence_fields,
            "follow_up_created": bool(result.follow_up_id),
        },
    )
    return result


@router.post(
    "/jobs/{job_id}/reanalyze",
    response_model=ProcessAudioResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run analysis for a job (audio must still be available)",
)
async def reanalyze(
    db: DbDep, principal: Annotated[CurrentUser, requires("ai:process")], job_id: uuid.UUID
) -> ProcessAudioResponse:
    service = _service(db, principal)
    job = await service.jobs.get_or_404(job_id)
    if job.audio_blob_name is None and job.status == JobStatus.APPLIED:
        raise ConflictError(
            "audio deleted",
            user_message=(
                "This recording was already processed and deleted for your privacy. "
                "Please add the details manually or record again."
            ),
        )
    job.status = JobStatus.QUEUED
    job.progress = 5
    job.error_code = None
    job.error_message = None
    await db.commit()
    await enqueue_job(job.id, principal.business_id)
    return ProcessAudioResponse(
        job_id=job.id,
        status=JobStatus.QUEUED,
        stage_label=job.stage_label,
        progress=job.progress,
    )
