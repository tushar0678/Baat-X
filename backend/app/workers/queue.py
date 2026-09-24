"""Redis/arq queue access used by the API side."""

from __future__ import annotations

import uuid

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config.logging import get_logger
from app.config.settings import get_settings

log = get_logger(__name__)
_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def enqueue_job(job_id: uuid.UUID, business_id: uuid.UUID) -> None:
    """Hand a processing job to the worker.

    `_job_id` makes the enqueue itself idempotent: re-submitting the same
    processing job never creates a duplicate queue entry.
    """
    try:
        pool = await get_pool()
        await pool.enqueue_job(
            "process_ai_job", str(job_id), str(business_id), _job_id=f"ai:{job_id}"
        )
        log.info("job_enqueued", job_id=str(job_id))
    except Exception:  # noqa: BLE001
        # The reconciliation cron re-queues anything left QUEUED, so the audio
        # is never lost - the user just waits a little longer.
        log.warning("job_enqueue_failed", job_id=str(job_id))


async def queue_healthy() -> bool:
    try:
        pool = await get_pool()
        await pool.ping()
    except Exception:  # noqa: BLE001
        return False
    return True


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
