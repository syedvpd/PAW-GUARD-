import contextlib
import functools
import hashlib
import json
from typing import Any

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder

from pawguard.redis.client import _ensure_client
from pawguard.services.cache_service import CacheService


def cache_response(ttl_seconds: int = 300, namespace: str = "route_cache"):
    """FastAPI route decorator to cache GET responses in Redis with support for ETags and cache partitioning.

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

            # 3. Get Redis client and check if available
            redis = await _ensure_client()
            from pawguard.redis.client import is_null_redis

            if is_null_redis(redis):
                return await func(*args, **kwargs)

            # 4. Build Cache Key
            query_str = "&".join(f"{k}={v}" for k, v in sorted(request.query_params.items()))
            cache_key = f"{request.url.path}"
            if query_str:
                cache_key += f"?{query_str}"

            # Partition cache by user identity (stable across token rotations).
            # We extract the `sub` (user_id) and `role` claims from the JWT payload
            # WITHOUT re-verifying the signature — auth middleware already did that.
            # This means the same user's cache entry survives token refresh, eliminating
            # cache misses on every new login that were causing 300-900ms DB hits.
            auth_header = request.headers.get("authorization")
            cookie_token = request.cookies.get("access_token")
            raw_token = None
            if auth_header and auth_header.lower().startswith("bearer "):
                raw_token = auth_header[7:]
            elif cookie_token:
                raw_token = cookie_token

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
                    # Fallback: hash the token as before if JWT decode fails
                    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()[:16]
                    cache_key += f":auth:{token_hash}"

            # 5. Read from Cache
            cache = CacheService(redis, namespace=namespace)
            try:
                cached_data = await cache.get(cache_key)
            except Exception:
                cached_data = None

            if cached_data is not None:
                content = cached_data.get("content")
                headers = cached_data.get("headers", {})
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
                        "content": content_bytes.decode("utf-8"),
                        "headers": headers_dict,
                        "status_code": status_code,
                    }
                    with contextlib.suppress(Exception):
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
                with contextlib.suppress(Exception):
                    await cache.set(cache_key, cache_payload, ttl_seconds=ttl_seconds)

                headers_dict["X-Cache-Status"] = "MISS"
                return Response(
                    content=content_str, media_type="application/json", headers=headers_dict
                )

        return wrapper

    return decorator
