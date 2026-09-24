"""Background tasks.

Every task opens its own session, is idempotent, and is safe to retry: arq
retries with exponential backoff and gives up after `job_max_tries`, at which
point the job row itself carries the user-facing error message.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config.logging import get_logger
from app.config.settings import get_settings
from app.db.session import session_scope
from app.models.conversation import AIProcessingJob
from app.models.enums import JobStatus, NotificationType
from app.models.tenancy import Business
from app.services.ai.factory import llm_provider, storage_provider, stt_provider
from app.services.ai.pipeline import AIProcessingService
from app.services.notifications.service import NotificationService
from app.services.reminders.followup_service import FollowUpService
from app.services.reports.report_service import ReportService

log = get_logger("worker")


async def process_ai_job(ctx: dict, job_id: str, business_id: str) -> str:
    job_uuid, business_uuid = uuid.UUID(job_id), uuid.UUID(business_id)
    async with session_scope() as session:
        business = await session.get(Business, business_uuid)
        if business is None:
            return "business_missing"

        service = AIProcessingService(
            session,
            business_id=business_uuid,
            llm=llm_provider(),
            stt=stt_provider(),
            storage=storage_provider(),
            timezone=business.timezone,
            country_code=business.country_code,
        )
        try:
            extraction = await service.process_job(job_uuid)
        except Exception:
            if ctx.get("job_try", 1) >= get_settings().job_max_tries:
                await _notify_failure(session, business_uuid, job_uuid)
            raise

        job = await service.jobs.get(job_uuid)
        await NotificationService(session, business_uuid).create(
            user_id=job.created_by_user_id if job else None,
            type=NotificationType.JOB_READY,
            title="Your conversation is ready",
            body="Review what BaatX understood and save it to your CRM.",
            dedupe_key=f"job_ready:{job_uuid}",
            data={"job_id": str(job_uuid), "extraction_id": str(extraction.id)},
        )
        return "ok"


async def _notify_failure(session, business_id: uuid.UUID, job_id: uuid.UUID) -> None:  # noqa: ANN001
    job = await session.get(AIProcessingJob, job_id)
    await NotificationService(session, business_id).create(
        user_id=job.created_by_user_id if job else None,
        type=NotificationType.JOB_FAILED,
        title="We couldn't process that recording",
        body="Something went wrong while processing your recording. Please try again.",
        dedupe_key=f"job_failed:{job_id}",
    )


async def sweep_reminders(ctx: dict) -> int:
    """Cron: mark overdue follow-ups and emit due-soon reminders for every tenant."""
    total = 0
    async with session_scope() as session:
        businesses = (
            await session.execute(select(Business).where(Business.is_active.is_(True)))
        ).scalars().all()
        for business in businesses:
            total += await FollowUpService(
                session, business.id, business.timezone
            ).sweep_due_reminders()
    log.info("reminder_sweep_completed", notifications=total)
    return total


async def generate_daily_reports(ctx: dict) -> int:
    """Cron: materialise yesterday's daily report per tenant from real rows."""
    count = 0
    async with session_scope() as session:
        businesses = (
            await session.execute(select(Business).where(Business.is_active.is_(True)))
        ).scalars().all()
        for business in businesses:
            service = ReportService(
                session, business.id, timezone=business.timezone, llm=llm_provider()
            )
            await service.daily((datetime.now(UTC) - timedelta(days=1)).date())
            count += 1
    return count


async def reconcile_stuck_jobs(ctx: dict) -> int:
    """Cron: re-queue jobs that never reached a worker, and expire ancient ones."""
    from app.workers.queue import enqueue_job

    requeued = 0
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    expiry = datetime.now(UTC) - timedelta(hours=6)
    async with session_scope() as session:
        stmt = (
            select(AIProcessingJob)
            .where(AIProcessingJob.status == JobStatus.QUEUED)
            .where(AIProcessingJob.created_at < cutoff)
            .limit(200)
        )
        for job in (await session.execute(stmt)).scalars().all():
            if job.created_at < expiry:
                job.status = JobStatus.FAILED
                job.error_code = "timed_out"
                job.error_message = (
                    "Something went wrong while processing your recording. Please try again."
                )
                continue
            await enqueue_job(job.id, job.business_id)
            requeued += 1
    log.info("stuck_jobs_reconciled", requeued=requeued)
    return requeued
