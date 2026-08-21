"""Unit tests for CacheService against the NullRedis stand-in.

``delete_prefix`` consumes ``scan_iter`` with ``async for`` (the redis-py
async-generator protocol). The ``_NullRedis`` fallback used when Redis is
unconfigured must no-op cleanly instead of raising TypeError, so admin RBAC
cache invalidation and portal stats purges degrade gracefully without Redis.
"""

import pytest

from pawguard.redis.client import _NullRedis
from pawguard.services.cache_service import CacheService


@pytest.mark.asyncio
async def test_delete_prefix_noops_without_redis() -> None:
    redis = _NullRedis()
    cache = CacheService(redis, namespace="rbac")

    # Admin role writes call delete_prefix("roles") whenever Redis is absent
    # (get_redis yields _NullRedis, not None) - this must not raise.
    await cache.delete_prefix("roles")


@pytest.mark.asyncio
async def test_scan_iter_is_async_generator() -> None:
    redis = _NullRedis()

    collected = [k async for k in redis.scan_iter(match="rbac:roles*")]
    assert collected == []


class MockRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.eval_script: str | None = None
        self.eval_args: list[str] = []

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        px: int | None = None,
        nx: bool | None = None,
    ) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> int:
        self.eval_script = script
        self.eval_args = list(keys_and_args)
        key = keys_and_args[0]
        token = keys_and_args[1]
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


@pytest.mark.asyncio
async def test_distributed_locks_with_mock_redis() -> None:
    mock_redis = MockRedis()
    cache = CacheService(mock_redis, namespace="test")  # type: ignore[arg-type]

    # Acquire lock should succeed the first time
    assert await cache.acquire_lock("my_lock", "token_1") is True
    assert mock_redis.store["test:my_lock"] == "token_1"

    # Acquire lock should fail when lock is already held
    assert await cache.acquire_lock("my_lock", "token_2") is False

    # Release lock with wrong token should fail and not remove lock
    assert await cache.release_lock("my_lock", "token_2") is False
    assert "test:my_lock" in mock_redis.store

    # Release lock with correct token should succeed and remove lock
    assert await cache.release_lock("my_lock", "token_1") is True
    assert "test:my_lock" not in mock_redis.store


@pytest.mark.asyncio
async def test_locks_fail_closed_without_redis() -> None:
    redis = _NullRedis()
    cache = CacheService(redis, namespace="test")

    # Distributed lock must fail closed when Redis is unavailable to prevent race conditions
    assert await cache.acquire_lock("my_lock", "token") is False
    assert await cache.release_lock("my_lock", "token") is False
