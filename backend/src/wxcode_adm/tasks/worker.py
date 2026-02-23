"""
arq worker configuration for wxcode-adm.

The arq worker runs as a SEPARATE PROCESS from the FastAPI app:
    arq wxcode_adm.tasks.worker.WorkerSettings

This module defines:
- test_job: simple job to verify worker is operational
- startup/shutdown hooks: verify DB connectivity, manage resources
- WorkerSettings: arq worker configuration class
- get_arq_pool: helper to enqueue jobs from FastAPI API code

arq uses Redis as its queue backend (same Redis instance as the API).
"""

import logging

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import text

from wxcode_adm.auth.email import send_reset_email, send_verification_email
from wxcode_adm.billing.email import send_payment_failed_email
from wxcode_adm.billing.service import process_stripe_event
from wxcode_adm.tenants.email import send_invitation_email
from wxcode_adm.config import settings
from wxcode_adm.db.engine import async_session_maker, engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


async def test_job(ctx: dict) -> str:
    """
    Test job to verify the arq worker is operational.

    Enqueue with:
        pool = await get_arq_pool()
        job = await pool.enqueue_job("test_job")
        print(f"Job {job.job_id} enqueued")
        await pool.aclose()
    """
    logger.info("test_job: arq worker is operational")
    return "arq worker is operational"


# ---------------------------------------------------------------------------
# Worker lifecycle hooks
# ---------------------------------------------------------------------------


async def startup(ctx: dict) -> None:
    """
    arq worker startup hook.

    Called once when the worker process starts.
    - Verifies PostgreSQL connectivity (fail fast if DB is unreachable)
    - Stores session_maker in ctx for use by jobs that need DB access
    """
    logger.info("arq worker startup: verifying PostgreSQL connectivity...")
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("arq worker startup: PostgreSQL connection verified.")

    # Store session_maker in ctx so jobs can create sessions as needed
    ctx["session_maker"] = async_session_maker
    logger.info("arq worker startup: complete.")


async def shutdown(ctx: dict) -> None:
    """
    arq worker shutdown hook.

    Called once when the worker process stops.
    Disposes the SQLAlchemy engine to close all pool connections.
    """
    logger.info("arq worker shutdown: disposing SQLAlchemy engine...")
    await engine.dispose()
    logger.info("arq worker shutdown: complete.")


# ---------------------------------------------------------------------------
# Worker settings
# ---------------------------------------------------------------------------


class WorkerSettings:
    """
    arq WorkerSettings class.

    arq reads this class to configure the worker process.
    Start the worker with:
        arq wxcode_adm.tasks.worker.WorkerSettings
    """

    functions = [
        test_job,
        send_verification_email,
        send_reset_email,
        send_invitation_email,
        process_stripe_event,
        send_payment_failed_email,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 300  # seconds


# ---------------------------------------------------------------------------
# Pool helper for enqueueing jobs from API code
# ---------------------------------------------------------------------------


async def get_arq_pool():
    """
    Create and return an arq connection pool for enqueueing jobs.

    Use this from API endpoints or background tasks to enqueue work.
    Caller is responsible for closing the pool with await pool.aclose().

    Example:
        pool = await get_arq_pool()
        try:
            job = await pool.enqueue_job("test_job")
            print(f"Job {job.job_id} enqueued")
        finally:
            await pool.aclose()
    """
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
