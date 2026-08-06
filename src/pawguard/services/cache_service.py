"""Thin, namespaced Redis wrapper. Every entry requires a TTL — no unbounded caching."""

import json
from typing import Any

from pawguard.redis.client import RedisClient

DEFAULT_TTL_SECONDS = 300


class CacheService:
    def __init__(self, redis: RedisClient, *, namespace: str = "pawguard") -> None:
        self._redis = redis
        self._namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def get(self, key: str) -> Any | None:
        raw = await self._redis.get(self._key(key))
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: Any, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        await self._redis.set(self._key(key), json.dumps(value), ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._redis.delete(self._key(key))

    async def delete_prefix(self, prefix: str) -> None:
        pattern = self._key(f"{prefix}*")
        async for k in self._redis.scan_iter(match=pattern):
            await self._redis.delete(k)

    async def acquire_lock(self, lock_key: str, token: str, expire_ms: int = 10000) -> bool:
        """Acquire a distributed lock with NX PX options."""
        try:
            from pawguard.redis.client import _NullRedis

            if isinstance(self._redis, _NullRedis):
                return True
            res = await self._redis.set(self._key(lock_key), token, px=expire_ms, nx=True)
            return bool(res)
        except Exception:
            return True

    async def release_lock(self, lock_key: str, token: str) -> bool:
        """Release a distributed lock atomically using Lua script to verify token ownership."""
        from pawguard.redis.client import _NullRedis

        if isinstance(self._redis, _NullRedis):
            return True

        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            res = await self._redis.eval(lua_script, 1, self._key(lock_key), token)
            return bool(res)
        except Exception:
            return False

