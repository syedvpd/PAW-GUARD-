import contextlib
import functools
import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder

from pawguard.redis.client import _ensure_client
from pawguard.services.cache_service import CacheService


class MemoryCache:
    """Thread-safe bounded in-memory LRU cache with per-item TTL expiration."""

    def __init__(self, max_entries: int = 5000) -> None:
        self._max = max_entries
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            if key not in self._cache:
                return None
            expiry, value = self._cache[key]
            if now > expiry:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        now = time.monotonic()
        expiry = now + ttl_seconds
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            elif len(self._cache) >= self._max:
                self._cache.popitem(last=False)
            self._cache[key] = (expiry, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            keys_to_del = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_del:
                del self._cache[k]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


_L1_CACHE = MemoryCache()


def get_l1_cache() -> MemoryCache:
    return _L1_CACHE


async def invalidate_route_cache(namespace: str) -> None:
    """Drop every cached response in a ``cache_response`` namespace from L1 memory and Redis."""
    _L1_CACHE.delete_prefix(f"{namespace}:")
    with contextlib.suppress(Exception):
        redis = await _ensure_client()
        from pawguard.redis.client import is_null_redis

        if not is_null_redis(redis):
            await CacheService(redis, namespace=namespace).delete_prefix("")


def cache_response(ttl_seconds: int = 300, namespace: str = "route_cache"):
    """FastAPI route decorator to cache GET responses in memory (L1) and Redis (L2) with ETag support.

    Partitions the cache using the Authorization header and access_token cookie to prevent
    privilege escalation and PII leakage between authenticated and anonymous users.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 1. Locate Request object in args or kwargs
            request = next((arg for arg in args if isinstance(arg, Request)), None)
            if not request:
                request = next((v for v in kwargs.values() if isinstance(v, Request)), None)

            # 2. Bypass cache if not a safe GET request or Request object is missing
            if not request or request.method != "GET":
                return await func(*args, **kwargs)

            # 3. Build Cache Key
            query_str = "&".join(f"{k}={v}" for k, v in sorted(request.query_params.items()))
            raw_key = f"{request.url.path}"
            if query_str:
                raw_key += f"?{query_str}"

            # Partition cache by user identity (stable across token rotations).
            auth_header = request.headers.get("authorization")
            cookie_token = request.cookies.get("access_token")
            raw_token = None
            if auth_header and auth_header.lower().startswith("bearer "):
                raw_token = auth_header[7:]
            elif cookie_token:
                raw_token = cookie_token

            cache_key = raw_key
            if raw_token:
                try:
                    import base64

                    # Decode JWT payload (middle segment) without signature verification
                    payload_b64 = raw_token.split(".")[1]
                    # Pad to valid base64 length
                    payload_b64 += "=" * (4 - len(payload_b64) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    user_id = str(payload.get("sub", ""))
                    role = str(payload.get("role", payload.get("roles", "")))
                    if user_id:
                        cache_key += f":uid:{user_id[:16]}"
                    if role:
                        cache_key += f":role:{hashlib.sha256(role.encode()).hexdigest()[:8]}"
                except Exception:
                    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()[:16]
                    cache_key += f":auth:{token_hash}"

            full_l1_key = f"{namespace}:{cache_key}"

            # 4. Check In-Memory L1 Cache first (< 0.1ms)
            cached_data = _L1_CACHE.get(full_l1_key)

            # 5. If missed in L1, check Redis L2 Cache
            if cached_data is None:
                with contextlib.suppress(Exception):
                    redis = await _ensure_client()
                    from pawguard.redis.client import is_null_redis

                    if not is_null_redis(redis):
                        cache = CacheService(redis, namespace=namespace)
                        cached_data = await cache.get(cache_key)
                        if cached_data is not None:
                            _L1_CACHE.set(full_l1_key, cached_data, ttl_seconds=ttl_seconds)

            if cached_data is not None:
                content = cached_data.get("content")
                headers = dict(cached_data.get("headers", {}))
                status_code = cached_data.get("status_code", 200)

                # Check If-None-Match ETag
                etag = headers.get("ETag") or headers.get("etag")
                if etag:
                    if_none_match = request.headers.get("if-none-match")
                    if if_none_match == etag:
                        return Response(
                            status_code=304,
                            headers={
                                "Cache-Control": headers.get(
                                    "Cache-Control", f"public, max-age={ttl_seconds}"
                                ),
                                "ETag": etag,
                                "X-Cache-Status": "HIT-304",
                            },
                        )

                headers["X-Cache-Status"] = "HIT"
                return Response(
                    content=content,
                    media_type="application/json",
                    status_code=status_code,
                    headers=headers,
                )

            # 6. Execute actual handler
            response = await func(*args, **kwargs)

            # 7. Extract content if Response, or serialize if Pydantic
            if isinstance(response, Response):
                status_code = response.status_code
                content_bytes = response.body
                headers_dict = dict(response.headers)

                if status_code == 200:
                    cache_payload = {
                        "content": bytes(content_bytes).decode("utf-8"),
                        "headers": headers_dict,
                        "status_code": status_code,
                    }
                    _L1_CACHE.set(full_l1_key, cache_payload, ttl_seconds=ttl_seconds)
                    with contextlib.suppress(Exception):
                        redis = await _ensure_client()
                        from pawguard.redis.client import is_null_redis

                        if not is_null_redis(redis):
                            cache = CacheService(redis, namespace=namespace)
                            await cache.set(cache_key, cache_payload, ttl_seconds=ttl_seconds)
                return response
            else:
                serializable = jsonable_encoder(response)
                content_str = json.dumps(serializable)
                etag = f'W/"{hashlib.sha256(content_str.encode("utf-8")).hexdigest()}"'

                headers_dict = {"Cache-Control": f"public, max-age={ttl_seconds}", "ETag": etag}

                cache_payload = {
                    "content": content_str,
                    "headers": headers_dict,
                    "status_code": 200,
                }
                _L1_CACHE.set(full_l1_key, cache_payload, ttl_seconds=ttl_seconds)
                with contextlib.suppress(Exception):
                    redis = await _ensure_client()
                    from pawguard.redis.client import is_null_redis

                    if not is_null_redis(redis):
                        cache = CacheService(redis, namespace=namespace)
                        await cache.set(cache_key, cache_payload, ttl_seconds=ttl_seconds)

                headers_dict["X-Cache-Status"] = "MISS"
                return Response(
                    content=content_str, media_type="application/json", headers=headers_dict
                )

        return wrapper

    return decorator
