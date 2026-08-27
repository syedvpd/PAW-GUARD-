import asyncio
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron

from pawguard.api.v1.router import api_v1_router  # noqa: F401  (side effects)
from pawguard.core.config import get_settings
from pawguard.core.logging import configure_logging, get_logger
from pawguard.core.metrics import increment_counter, observe_histogram
from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.outbox.service import OutboxService
from pawguard.workers.jobs.companion_pet_jobs import send_companion_pet_reminders
from pawguard.workers.jobs.email_jobs import (
    send_email_verification_email_job,
    send_notification_email_job,
    send_password_reset_email_job,
)
from pawguard.workers.jobs.lost_found_jobs import broadcast_lost_pet_alert
from pawguard.workers.jobs.scheduled_jobs import (
    check_inventory_expiry,
    check_inventory_low_stock,
    check_vaccination_renewals,
    post_adoption_followups,
    process_sponsorship_charges,
    send_volunteer_shift_reminders,
)

logger = get_logger(__name__)

settings = get_settings()


def _track_failures(fn: Callable[..., Awaitable[Any]]) -> Any:
    """Log and instrument job execution duration, success, retries, and failures.

    ARQ 0.28 has no ``on_job_failure`` hook, so each job is wrapped at registration time.
    """

    @wraps(fn)
    async def wrapper(ctx: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        job_name = fn.__name__
        start = time.perf_counter()
        increment_counter("worker_jobs_total", {"job": job_name, "status": "started"})
        try:
            res = await fn(ctx, *args, **kwargs)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            observe_histogram("worker_job_duration_ms", elapsed_ms, {"job": job_name})
            increment_counter("worker_jobs_total", {"job": job_name, "status": "success"})
            return res
        except Retry:
            increment_counter("worker_job_retries_total", {"job": job_name})
            raise
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            observe_histogram("worker_job_duration_ms", elapsed_ms, {"job": job_name})
            logger.error(
                "arq_job_failed",
                job=job_name,
                job_id=ctx.get("job_id"),
                job_try=ctx.get("job_try"),
                args=args,
                kwargs=kwargs,
                error_type=exc.__class__.__name__,
                error=str(exc),
                exc_info=exc,
            )
            increment_counter("arq_job_failed_total", {"job": job_name})
            increment_counter("worker_job_failures_total", {"job": job_name})
            increment_counter("worker_jobs_total", {"job": job_name, "status": "failed"})
            raise

    return wrapper


async def outbox_poller_loop(ctx: dict[str, Any]) -> None:
    logger.info("outbox_poller_loop_started")
    from pawguard.workers.pool import _ensure_pool

    pool = await _ensure_pool()
    current_delay = 2

    while True:
        processed = 0
        try:
            async with AsyncSessionLocal() as session, session.begin():
                processed = await OutboxService.process_pending_events(session, pool)
                if processed > 0:
                    logger.debug(f"Outbox processed {processed} events.")
        except Exception as e:
            logger.error("outbox_poller_loop_error", error=str(e))
            processed = 0

        if processed > 0:
            current_delay = 5
        else:
            if current_delay == 5:
                current_delay = 30
            elif current_delay == 30:
                current_delay = 120
            elif current_delay == 120:
                current_delay = 300
            else:
                current_delay = 300

        await asyncio.sleep(current_delay)


async def startup(ctx: dict[str, object]) -> None:
    configure_logging()
    logger.info("arq_worker_startup", max_tries=WorkerSettings.max_tries)
    await asyncio.sleep(0)
    ctx["outbox_task"] = asyncio.create_task(outbox_poller_loop(ctx))


async def shutdown(ctx: dict[str, object]) -> None:
    logger.info("arq_worker_shutdown")
    task = ctx.get("outbox_task")
    if isinstance(task, asyncio.Task) and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("outbox_task_cancelled")
            raise


_send_password_reset_email_job = _track_failures(send_password_reset_email_job)
_send_email_verification_email_job = _track_failures(send_email_verification_email_job)
_send_notification_email_job = _track_failures(send_notification_email_job)

_check_inventory_low_stock = _track_failures(check_inventory_low_stock)
_check_inventory_expiry = _track_failures(check_inventory_expiry)
_check_vaccination_renewals = _track_failures(check_vaccination_renewals)
_post_adoption_followups = _track_failures(post_adoption_followups)
_process_sponsorship_charges = _track_failures(process_sponsorship_charges)
_send_companion_pet_reminders = _track_failures(send_companion_pet_reminders)
_broadcast_lost_pet_alert = _track_failures(broadcast_lost_pet_alert)
_send_volunteer_shift_reminders = _track_failures(send_volunteer_shift_reminders)


class WorkerSettings:
    # Async email jobs are retried up to 5 times with backoff (see email_jobs.py).
    max_tries = 5
    poll_delay_seconds = float(settings.arq_poll_delay_seconds)
    functions: list[Any] = [
        _send_password_reset_email_job,
        _send_email_verification_email_job,
        _send_notification_email_job,
        _check_inventory_low_stock,
        _check_inventory_expiry,
        _check_vaccination_renewals,
        _post_adoption_followups,
        _process_sponsorship_charges,
        _send_companion_pet_reminders,
        _broadcast_lost_pet_alert,
        _send_volunteer_shift_reminders,
    ]
    cron_jobs = [
        # Scheduled cron jobs: 2 tries is enough — a missed run just fires again
        # on the next cycle.
        cron(_check_inventory_low_stock, hour={0, 12}, minute={0}, max_tries=2),
        cron(_check_inventory_expiry, hour={9}, minute={0}, max_tries=2),
        cron(_check_vaccination_renewals, hour={9}, minute={30}, max_tries=2),
        cron(_post_adoption_followups, hour={10}, minute={0}, max_tries=2),
        cron(_process_sponsorship_charges, hour={8}, minute={0}, max_tries=2),
        cron(_send_companion_pet_reminders, hour={9}, minute={45}, max_tries=2),
        cron(_send_volunteer_shift_reminders, hour={11}, minute={0}, max_tries=2),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
