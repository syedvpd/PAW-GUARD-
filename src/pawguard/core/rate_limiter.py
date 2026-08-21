"""Redis-backed rate limiter for per-endpoint and per-user throttling.

Uses a sliding window counter approach via Redis INCR + EXPIRE.
Every endpoint that needs protection declares a rate limit using
the ``rate_limit`` dependency.

Usage in a router::

    from pawguard.core.rate_limiter import rate_limit

    @router.post("/login")
    async def login(_: Annotated[None, Depends(rate_limit("login", 10, 60))]):
        ...
"""

import time

from fastapi import Depends, Request

from pawguard.core.exceptions import TooManyRequestsError
from pawguard.redis.client import RedisClient, get_redis


class _RateLimitDependency:
    def __init__(self, prefix: str, max_requests: int, window_seconds: int) -> None:
        self._prefix = prefix
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def __call__(self, request: Request, redis: RedisClient = Depends(get_redis)) -> None:
        from pawguard.core.config import get_settings

        if not get_settings().rate_limiting_enabled:
            return
        user_key = _resolve_user_key(request)
        bucket = f"rate_limit:{self._prefix}:{user_key}:{int(time.time()) // self._window_seconds}"
        count = await redis.incr(bucket)
        if count == 1:
            await redis.expire(bucket, self._window_seconds + 1)
        if count > self._max_requests:
            raise TooManyRequestsError("Too many requests. Please try again later.")


def resolve_client_ip(request: Request) -> str:
    """Securely resolve real client IP, avoiding header spoofing.

    If behind Cloudflare, CF-Connecting-IP is used. Otherwise, the rightmost
    entry of X-Forwarded-For is returned since the last proxy appends the caller's
    connecting IP to the end.
    """
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def _resolve_user_key(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        return str(user_id)
    return resolve_client_ip(request)


def rate_limit(
    prefix: str, max_requests: int = 10, window_seconds: int = 60
) -> _RateLimitDependency:
    return _RateLimitDependency(prefix, max_requests, window_seconds)
