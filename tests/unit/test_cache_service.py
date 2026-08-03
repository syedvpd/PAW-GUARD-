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
