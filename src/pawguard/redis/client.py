"""Async Redis client singleton, the `get_redis` FastAPI dependency, and a safe type alias.

`RedisClient` is a type alias that resolves to `Redis[str]` during type-checking
and plain `Redis` at runtime, because redis-py 5.x defines `Redis` as a generic type
in its stubs but the runtime class does not support subscripting in Python 3.13.
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from redis.asyncio import ConnectionPool, Redis

from pawguard.core.config import get_settings

if TYPE_CHECKING:
    from redis.asyncio import Redis as _Redis
    RedisClient = _Redis[str]
else:
    RedisClient = Redis

_settings = get_settings()

_pool = ConnectionPool.from_url(  # type: ignore[var-annotated]
    _settings.redis_url,
    decode_responses=True,
    max_connections=100,
)

redis_client: RedisClient = Redis(connection_pool=_pool)  # type: ignore[assignment]


async def get_redis() -> AsyncGenerator[RedisClient]:
    yield redis_client


async def ping_redis() -> bool:
    try:
        return bool(await redis_client.ping())
    except Exception:
        return False
