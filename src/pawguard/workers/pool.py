"""ARQ Redis pool used by routers/services to enqueue background jobs.

Connection is lazy and degrades gracefully — if Redis/ARQ is unreachable the
API must still serve requests (e.g. registration, password reset) instead of
500ing just because a background email job couldn't be queued.
"""

from collections.abc import AsyncGenerator
from typing import Any

import structlog
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from pawguard.core.config import get_settings

logger = structlog.get_logger(__name__)

_pool: ArqRedis | None = None


class _NullArqPool:
    """Stand-in when Redis/ARQ is unreachable — enqueue calls are no-ops."""

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> None:
        logger.warning("arq_pool_unavailable_job_dropped", job=args[0] if args else None)
        return None


async def _ensure_pool() -> ArqRedis:
    global _pool
    if _pool is not None:
        return _pool
    try:
        settings = get_settings()
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception:
        logger.warning("arq_pool_unreachable_falling_back_to_noop")
        _pool = _NullArqPool()  # type: ignore[assignment]
    return _pool  # type: ignore[return-value]


async def get_arq_pool() -> AsyncGenerator[ArqRedis]:
    yield await _ensure_pool()
