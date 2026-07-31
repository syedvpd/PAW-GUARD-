"""ARQ worker entrypoint. Run with: `arq pawguard.workers.arq_worker.WorkerSettings`."""

from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from pawguard.core.config import get_settings
from pawguard.core.logging import configure_logging
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

settings = get_settings()


async def startup(ctx: dict[str, object]) -> None:
    configure_logging()


class WorkerSettings:
    functions: list[Any] = [
        send_password_reset_email_job,
        send_email_verification_email_job,
        send_notification_email_job,
        check_inventory_low_stock,
        check_inventory_expiry,
        check_vaccination_renewals,
        post_adoption_followups,
        process_sponsorship_charges,
    ]
    cron_jobs = [
        cron(check_inventory_low_stock, hour={0, 12}, minute={0}),
        cron(check_inventory_expiry, hour={9}, minute={0}),
        cron(check_vaccination_renewals, hour={9}, minute={30}),
        cron(post_adoption_followups, hour={10}, minute={0}),
        cron(process_sponsorship_charges, hour={8}, minute={0}),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
