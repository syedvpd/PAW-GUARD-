"""ARQ Redis pool used by routers/services to enqueue background jobs."""

from collections.abc import AsyncGenerator

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from pawguard.core.config import get_settings

_pool: ArqRedis | None = None


async def get_arq_pool() -> AsyncGenerator[ArqRedis]:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield _pool
