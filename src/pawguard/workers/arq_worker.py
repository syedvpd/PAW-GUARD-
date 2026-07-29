"""ARQ worker entrypoint. Run with: `arq pawguard.workers.arq_worker.WorkerSettings`."""

from typing import Any

from arq.connections import RedisSettings

from pawguard.core.config import get_settings
from pawguard.core.logging import configure_logging
from pawguard.workers.jobs.email_jobs import (
    send_email_verification_email_job,
    send_password_reset_email_job,
)

settings = get_settings()


async def startup(ctx: dict[str, object]) -> None:
    configure_logging()


class WorkerSettings:
    functions: list[Any] = [send_password_reset_email_job, send_email_verification_email_job]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
