"""Async Redis client singleton, the `get_redis` FastAPI dependency, and a safe type alias.

`RedisClient` is a type alias that resolves to `Redis[str]` during type-checking
and plain `Redis` at runtime, because redis-py 5.x defines `Redis` as a generic type
in its stubs but the runtime class does not support subscripting in Python 3.13.

Connection is lazy — Redis is optional.  If unavailable the application still starts
and rate-limiting / caching degrade gracefully.
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from redis.asyncio import ConnectionPool, Redis

from pawguard.core.config import get_settings

if TYPE_CHECKING:
    from redis.asyncio import Redis as _Redis
    RedisClient = _Redis[str]
else:
    RedisClient = Redis

_settings = get_settings()

_pool: Any = None
_client: RedisClient | None = None


class _NullRedis:
    """Stand-in when real Redis is unreachable — all operations no-op."""

    async def get(self, key: str) -> None:
        return None

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        return None

    async def delete(self, key: str) -> None:
        return None

    async def incr(self, key: str) -> int:
        return 0

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def ping(self) -> bool:
        return False

    async def scan_iter(self, match: str = "", count: int | None = None) -> list[str]:
        return []


async def _ensure_client() -> RedisClient:
    global _pool, _client
    if _client is not None:
        return _client
    try:
        _pool = ConnectionPool.from_url(
            _settings.redis_url,
            decode_responses=True,
            max_connections=100,
        )
        _client = Redis(connection_pool=_pool)  # type: ignore[assignment]
        assert _client is not None
        await _client.ping()
    except Exception:
        _client = _NullRedis()  # type: ignore[assignment]
    return _client  # type: ignore[no-any-return]


async def get_redis() -> AsyncGenerator[RedisClient]:
    yield await _ensure_client()


async def ping_redis() -> bool:
    try:
        client = await _ensure_client()
        return bool(await client.ping())
    except Exception:
        return False
