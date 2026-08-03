"""Shared ARQ retry helpers: exponential backoff for transient job failures."""

from typing import Any

_ONE_DAY = 24 * 60 * 60


def retry_defer(ctx: dict[str, Any], *, base_seconds: int = 30) -> int:
    """Exponential backoff delay in seconds for the current attempt.

    ``job_try`` is 1 on the first run, so the first retry waits ``base``
    seconds, the second ``2 * base``, and so on, capped at 24 hours so a
    persistently failing job never pins the queue with absurd delays.
    """
    job_try = ctx.get("job_try") or 1
    if not isinstance(job_try, int):
        job_try = 1
    delay = min(base_seconds * (2 ** (job_try - 1)), _ONE_DAY)
    return int(delay)
