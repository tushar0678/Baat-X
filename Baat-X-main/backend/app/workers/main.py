"""arq worker entrypoint: `arq app.workers.main.WorkerSettings`."""

from __future__ import annotations

from arq import cron

from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings
from app.db.session import dispose_engine
from app.services.ai.factory import close_providers
from app.workers.queue import redis_settings
from app.workers.tasks import (
    generate_daily_reports,
    process_ai_job,
    reconcile_stuck_jobs,
    sweep_reminders,
)

log = get_logger("worker")


async def startup(ctx: dict) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log.info("worker_started", environment=settings.environment)


async def shutdown(ctx: dict) -> None:
    await close_providers()
    await dispose_engine()


class WorkerSettings:
    functions = [process_ai_job]
    cron_jobs = [
        cron(sweep_reminders, minute={0, 15, 30, 45}, run_at_startup=False),
        cron(reconcile_stuck_jobs, minute={5, 35}),
        cron(generate_daily_reports, hour=1, minute=10),  # UTC
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    max_jobs = 10
    job_timeout = get_settings().job_timeout_seconds
    max_tries = get_settings().job_max_tries
    keep_result = 3600
    health_check_interval = 60
