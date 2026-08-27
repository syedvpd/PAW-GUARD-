"""Thin, namespaced Redis wrapper. Every entry requires a TTL — no unbounded caching."""

import json
import time
from typing import Any

from pawguard.core.metrics import increment_counter, observe_histogram
from pawguard.redis.client import RedisClient

DEFAULT_TTL_SECONDS = 300


class CacheService:
    def __init__(self, redis: RedisClient, *, namespace: str = "pawguard") -> None:
        self._redis = redis
        self._namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def get(self, key: str) -> Any | None:
        start = time.perf_counter()
        try:
            raw = await self._redis.get(self._key(key))
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            observe_histogram(
                "redis_operation_duration_ms",
                elapsed_ms,
                {"op": "get", "namespace": self._namespace},
            )

            if raw is not None:
                increment_counter("redis_cache_hits_total", {"namespace": self._namespace})
                increment_counter(
                    "redis_operations_total",
                    {"op": "get", "namespace": self._namespace, "status": "hit"},
                )
                return json.loads(raw)
            increment_counter("redis_cache_misses_total", {"namespace": self._namespace})
            increment_counter(
                "redis_operations_total",
                {"op": "get", "namespace": self._namespace, "status": "miss"},
            )
            return None
        except Exception:
            increment_counter(
                "redis_operations_total",
                {"op": "get", "namespace": self._namespace, "status": "error"},
            )
            raise

    async def set(self, key: str, value: Any, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        start = time.perf_counter()
        try:
            await self._redis.set(self._key(key), json.dumps(value), ex=ttl_seconds)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            observe_histogram(
                "redis_operation_duration_ms",
                elapsed_ms,
                {"op": "set", "namespace": self._namespace},
            )
            increment_counter(
                "redis_operations_total",
                {"op": "set", "namespace": self._namespace, "status": "ok"},
            )
        except Exception:
            increment_counter(
                "redis_operations_total",
                {"op": "set", "namespace": self._namespace, "status": "error"},
            )
            raise

    async def delete(self, key: str) -> None:
        start = time.perf_counter()
        try:
            await self._redis.delete(self._key(key))
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            observe_histogram(
                "redis_operation_duration_ms",
                elapsed_ms,
                {"op": "delete", "namespace": self._namespace},
            )
            increment_counter(
                "redis_operations_total",
                {"op": "delete", "namespace": self._namespace, "status": "ok"},
            )
        except Exception:
            increment_counter(
                "redis_operations_total",
                {"op": "delete", "namespace": self._namespace, "status": "error"},
            )
            raise

    async def delete_prefix(self, prefix: str) -> None:
        start = time.perf_counter()
        try:
            pattern = self._key(f"{prefix}*")
            async for k in self._redis.scan_iter(match=pattern):
                await self._redis.delete(k)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            observe_histogram(
                "redis_operation_duration_ms",
                elapsed_ms,
                {"op": "delete_prefix", "namespace": self._namespace},
            )
            increment_counter(
                "redis_operations_total",
                {"op": "delete_prefix", "namespace": self._namespace, "status": "ok"},
            )
        except Exception:
            increment_counter(
                "redis_operations_total",
                {"op": "delete_prefix", "namespace": self._namespace, "status": "error"},
            )
            raise

    async def acquire_lock(self, lock_key: str, token: str, expire_ms: int = 10000) -> bool:
        """Acquire a distributed lock with NX PX options. Fails closed (False) if Redis is unavailable."""
        start = time.perf_counter()
        try:
            from pawguard.redis.client import is_null_redis

            if is_null_redis(self._redis):
                increment_counter(
                    "redis_operations_total",
                    {"op": "acquire_lock", "namespace": self._namespace, "status": "unavailable"},
                )
                return False
            res = await self._redis.set(self._key(lock_key), token, px=expire_ms, nx=True)
            ok = bool(res)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            observe_histogram(
                "redis_operation_duration_ms",
                elapsed_ms,
                {"op": "acquire_lock", "namespace": self._namespace},
            )
            increment_counter(
                "redis_operations_total",
                {
                    "op": "acquire_lock",
                    "namespace": self._namespace,
                    "status": "acquired" if ok else "busy",
                },
            )
            return ok
        except Exception:
            increment_counter(
                "redis_operations_total",
                {"op": "acquire_lock", "namespace": self._namespace, "status": "error"},
            )
            return False

    async def release_lock(self, lock_key: str, token: str) -> bool:
        """Release a distributed lock atomically using Lua script to verify token ownership."""
        start = time.perf_counter()
        from pawguard.redis.client import is_null_redis

        if is_null_redis(self._redis):
            increment_counter(
                "redis_operations_total",
                {"op": "release_lock", "namespace": self._namespace, "status": "unavailable"},
            )
            return False

        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            res = await self._redis.eval(lua_script, 1, self._key(lock_key), token)
            ok = bool(res)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            observe_histogram(
                "redis_operation_duration_ms",
                elapsed_ms,
                {"op": "release_lock", "namespace": self._namespace},
            )
            increment_counter(
                "redis_operations_total",
                {
                    "op": "release_lock",
                    "namespace": self._namespace,
                    "status": "released" if ok else "mismatch",
                },
            )
            return ok
        except Exception:
            increment_counter(
                "redis_operations_total",
                {"op": "release_lock", "namespace": self._namespace, "status": "error"},
            )
            return False
