"""ARQ Redis pool used by routers/services to enqueue background jobs.

Connection is lazy and degrades gracefully — if Redis/ARQ is unreachable the
API must still serve requests (e.g. registration, password reset) instead of
500ing just because a background email job couldn't be queued.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings

from pawguard.core.config import get_settings

logger = structlog.get_logger(__name__)

_pool: Any = None


class _NullArqPool:
    """Stand-in when Redis/ARQ is unreachable — enqueue calls are no-ops."""

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(0)
        from pawguard.core.config import get_settings
        settings = get_settings()
        job_name = args[0] if args else None
        if job_name:
            if settings.environment == "test":
                logger.info("Test environment: skipping enqueue_job in-process fallback", job=job_name)
                return "mock_job_id"
            logger.info("arq_pool_unavailable_falling_back_to_in_process", job=job_name)
            try:
                from pawguard.modules.outbox.service import _dispatch_job_direct
                await _dispatch_job_direct(job_name, kwargs)
                return "in_process_success"
            except Exception as exc:
                logger.error("in_process_job_dispatch_failed", job=job_name, error=str(exc))
                return None
        logger.warning("arq_pool_unavailable_job_dropped", job=job_name)
        return None


class _SafeArqPool:
    """Wrapper around ArqRedis pool that traps any connection errors during enqueue_job."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> Any:
        from pawguard.core.config import get_settings
        settings = get_settings()
        job_name = args[0] if args else None

        if settings.force_in_process_jobs:
            if job_name:
                logger.info("force_in_process_jobs_enabled_dispatching", job=job_name)
                try:
                    from pawguard.modules.outbox.service import _dispatch_job_direct
                    await _dispatch_job_direct(job_name, kwargs)
                    return "in_process_success"
                except Exception as exc:
                    logger.error("in_process_job_dispatch_failed", job=job_name, error=str(exc))
                    return None
            return None

        try:
            return await self._inner.enqueue_job(*args, **kwargs)
        except Exception as exc:
            logger.warning("arq_pool_enqueue_failed_falling_back", error=str(exc))
            if job_name:
                if settings.environment == "test":
                    logger.info("Test environment: skipping arq enqueue fallback to in-process", job=job_name)
                    return "mock_job_id"
                logger.info("arq_pool_enqueue_failed_falling_back_to_in_process", job=job_name)
                try:
                    from pawguard.modules.outbox.service import _dispatch_job_direct
                    await _dispatch_job_direct(job_name, kwargs)
                    return "in_process_success"
                except Exception as exc_inner:
                    logger.error("in_process_job_dispatch_failed", job=job_name, error=str(exc_inner))
                    return None
            return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


async def _ensure_pool() -> Any:
    global _pool
    if _pool is not None:
        return _pool
    settings = get_settings()
    if settings.disable_redis:
        logger.info("redis_disabled_falling_back_to_noop_pool")
        _pool = _NullArqPool()
        return _pool
    try:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        redis_settings.conn_timeout = 2.0
        redis_settings.conn_retries = 2
        inner_pool = await create_pool(redis_settings)
        _pool = _SafeArqPool(inner_pool)  # type: ignore[assignment]
    except Exception:
        logger.warning("arq_pool_unreachable_falling_back_to_noop")
        _pool = _NullArqPool()  # type: ignore[assignment]
    return _pool  # type: ignore[return-value]


async def get_arq_pool() -> AsyncGenerator[Any]:
    yield await _ensure_pool()
