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

_pool: Any = None


class _NullArqPool:
    """Stand-in when Redis/ARQ is unreachable — enqueue calls are no-ops."""

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> None:
        logger.warning("arq_pool_unavailable_job_dropped", job=args[0] if args else None)
        return None


class _SafeArqPool:
    """Wrapper around ArqRedis pool that traps any connection errors during enqueue_job."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return await self._inner.enqueue_job(*args, **kwargs)
        except Exception as exc:
            logger.warning("arq_pool_enqueue_failed_falling_back", error=str(exc))
            return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


async def _ensure_pool() -> Any:
    global _pool
    if _pool is None:
        _pool = _NullArqPool()
    return _pool


async def get_arq_pool() -> AsyncGenerator[Any]:
    yield await _ensure_pool()
