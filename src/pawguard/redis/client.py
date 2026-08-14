"""Async Redis client singleton, the `get_redis` FastAPI dependency, and a safe type alias.

`RedisClient` is a type alias that resolves to `Redis[str]` during type-checking
and plain `Redis` at runtime, because redis-py 5.x defines `Redis` as a generic type
in its stubs but the runtime class does not support subscripting in Python 3.13.

Connection is lazy — Redis is optional.  If unavailable the application still starts
and rate-limiting / caching degrade gracefully.
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, cast

from redis.asyncio import Redis

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

    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        px: int | None = None,
        nx: bool | None = None,
    ) -> Any:
        return None

    async def delete(self, key: str) -> None:
        return None

    async def incr(self, key: str) -> int:
        return 0

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        return None

    async def ping(self) -> bool:
        return False

    async def scan_iter(self, match: str = "", count: int | None = None):
        """No-op async generator mirroring redis-py's scan_iter protocol.

        ``CacheService.delete_prefix`` consumes scan_iter with ``async for``.
        If this returned a coroutine yielding a list, ``async for`` would raise
        TypeError the moment Redis is unavailable (e.g. RBAC cache invalidation
        or portal stats purges in dev/CI) instead of gracefully no-op'ing.
        """
        return
        yield  # pragma: no cover — marks this function as an async generator

    async def geoadd(self, name: str, *args: Any, **kwargs: Any) -> int:
        return 0

    async def geosearch(self, name: str, *args: Any, **kwargs: Any) -> list[Any]:
        return []




_redis_available: bool | None = None

async def _ensure_client() -> RedisClient:
    global _pool, _client, _redis_available
    if _client is not None:
        return _client
    if _redis_available is False:
        _client = cast(RedisClient, _NullRedis())
        return _client
    try:
        test_client = Redis.from_url(
            _settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.1,
            socket_timeout=0.1,
            retry_on_timeout=False,
        )
        await test_client.ping()
        _redis_available = True
        _client = cast(RedisClient, test_client)
    except Exception:
        _redis_available = False
        _client = cast(RedisClient, _NullRedis())
    return _client


async def get_redis() -> AsyncGenerator[RedisClient]:
    yield await _ensure_client()


async def ping_redis() -> bool:
    try:
        client = await _ensure_client()
        return bool(await client.ping())
    except Exception:
        return False
