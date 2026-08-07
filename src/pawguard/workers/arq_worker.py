"""ARQ worker entrypoint. Run with: `arq pawguard.workers.arq_worker.WorkerSettings`."""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron

# Importing the versioned API router registers every ORM model in the worker
# process (the web app does the same in main.py). Without it, string-referenced
# relationships (e.g. AdoptionApplication.dog -> "DogProfile") fail to resolve
# at mapper configuration time and the first scheduled job query crashes.
from pawguard.api.v1.router import api_v1_router  # noqa: F401  (side effects)
from pawguard.core.config import get_settings
from pawguard.core.logging import configure_logging, get_logger
from pawguard.core.metrics import increment_counter
from pawguard.workers.jobs.email_jobs import (
    send_email_verification_email_job,
    send_notification_email_job,
    send_password_reset_email_job,
)
from pawguard.workers.jobs.scheduled_jobs import (
    check_inventory_expiry,
    check_inventory_low_stock,
    check_vaccination_renewals,
    post_adoption_followups,
    process_sponsorship_charges,
)

logger = get_logger(__name__)

settings = get_settings()


def _track_failures(fn: Callable[..., Awaitable[Any]]) -> Any:
    """Log and count every job failure, then re-raise so ARQ retries apply.

    ARQ 0.28 has no ``on_job_failure`` hook (``on_job_end`` receives only the
    context, not the result), so each job is wrapped at registration time. The
    counter ``arq_job_failed_total`` is labeled by job name.
    """

    @wraps(fn)
    async def wrapper(ctx: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(ctx, *args, **kwargs)
        except Retry:
            # A deliberate, scheduled retry is not a terminal failure: let ARQ
            # re-queue the job and keep it out of the failure metric/log.
            raise
        except Exception as exc:
            logger.error(
                "arq_job_failed",
                job=fn.__name__,
                job_id=ctx.get("job_id"),
                job_try=ctx.get("job_try"),
                args=args,
                kwargs=kwargs,
                error_type=exc.__class__.__name__,
                error=str(exc),
                exc_info=exc,
            )
            increment_counter("arq_job_failed_total", {"job": fn.__name__})
            raise

    return wrapper


async def startup(ctx: dict[str, object]) -> None:
    configure_logging()

_send_password_reset_email_job = _track_failures(send_password_reset_email_job)
_send_email_verification_email_job = _track_failures(send_email_verification_email_job)
_send_notification_email_job = _track_failures(send_notification_email_job)

_check_inventory_low_stock = _track_failures(check_inventory_low_stock)
_check_inventory_expiry = _track_failures(check_inventory_expiry)
_check_vaccination_renewals = _track_failures(check_vaccination_renewals)
_post_adoption_followups = _track_failures(post_adoption_followups)
_process_sponsorship_charges = _track_failures(process_sponsorship_charges)


class WorkerSettings:
    # Async email jobs are retried up to 5 times with backoff (see email_jobs.py).
    max_tries = 5
    functions: list[Any] = [
        _send_password_reset_email_job,
        _send_email_verification_email_job,
        _send_notification_email_job,
        _check_inventory_low_stock,
        _check_inventory_expiry,
        _check_vaccination_renewals,
        _post_adoption_followups,
        _process_sponsorship_charges,
    ]
    cron_jobs = [
        # Scheduled cron jobs: 2 tries is enough — a missed run just fires again
        # on the next cycle.
        cron(_check_inventory_low_stock, hour={0, 12}, minute={0}, max_tries=2),
        cron(_check_inventory_expiry, hour={9}, minute={0}, max_tries=2),
        cron(_check_vaccination_renewals, hour={9}, minute={30}, max_tries=2),
        cron(_post_adoption_followups, hour={10}, minute={0}, max_tries=2),
        cron(_process_sponsorship_charges, hour={8}, minute={0}, max_tries=2),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
