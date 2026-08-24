"""Middleware to handle API request idempotency using Redis caching."""

import asyncio
import base64
import hashlib
import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pawguard.core.constants import ACCESS_TOKEN_COOKIE_NAME
from pawguard.core.security import parse_access_token_claims
from pawguard.redis.client import RedisClient, _ensure_client, _NullRedis
from pawguard.services.cache_service import CacheService

logger = logging.getLogger(__name__)


async def _resolve_redis(request: Request) -> RedisClient:
    """Resolves the Redis client, honoring dependency overrides if present (e.g. in tests)."""
    dependency_overrides = getattr(request.app, "dependency_overrides", {})
    from pawguard.redis.client import get_redis

    override = dependency_overrides.get(get_redis)
    if override:
        try:
            import inspect

            res = override()
            if hasattr(res, "__anext__"):
                # Handle async generator override
                async for client in res:
                    return client
            elif inspect.iscoroutine(res):
                return await res
            return res
        except Exception as e:
            logger.warning(f"Failed to resolve overridden Redis client: {e}")
    return await _ensure_client()


def _extract_user_id(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
    else:
        token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if token:
        try:
            claims = parse_access_token_claims(token)
            return str(claims.user_id)
        except Exception:
            pass
    return "anonymous"


def _build_hit_response(cached_resp: dict[str, Any]) -> Response:
    body_decoded = base64.b64decode(cached_resp["body"])
    headers = dict(cached_resp["headers"])
    headers["X-Cache-Idempotency"] = "HIT"
    return Response(
        content=body_decoded,
        status_code=cached_resp["status_code"],
        headers=headers,
        media_type=headers.get("content-type"),
    )


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Enforces API Idempotency via Idempotency-Key or X-Idempotency-Key headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        # Check if the path corresponds to one of the financial endpoints
        from pawguard.core.config import get_settings

        settings = get_settings()
        prefix = settings.api_v1_prefix

        financial_paths = {
            f"{prefix}/donations/checkout",
            f"{prefix}/donations/sponsorships",
            f"{prefix}/donations/recurring",
        }

        is_financial_route = request.method == "POST" and request.url.path in financial_paths

        idempotency_key = request.headers.get("idempotency-key") or request.headers.get(
            "x-idempotency-key"
        )
        if not idempotency_key and not is_financial_route:
            return await call_next(request)

        redis = await _resolve_redis(request)
        if isinstance(redis, _NullRedis):
            logger.warning("Idempotency requested but Redis is unreachable. Falling back.")
            return await call_next(request)

        cache_service = CacheService(redis, namespace="idempotency")

        body_bytes = await request.body()

        async def receive():
            await asyncio.sleep(0)
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request._receive = receive

        user_id = _extract_user_id(request)
        query_str = str(request.query_params)
        payload_hash = hashlib.sha256(
            f"{request.method}:{request.url.path}:{query_str}:".encode() + body_bytes
        ).hexdigest()

        if not idempotency_key:
            idempotency_key = f"auto-idempotency:{payload_hash}"

        if not (10 <= len(idempotency_key) <= 128):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Invalid Idempotency-Key format."},
            )

        redis_key = f"{idempotency_key}:{user_id}"
        cached = await cache_service.get(redis_key)
        if cached:
            if cached.get("status") == "processing":
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "error": "Request is already in flight. Please retry later.",
                        "code": "IDEMPOTENCY_IN_FLIGHT",
                    },
                )
            if cached.get("request_hash") != payload_hash:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "Idempotency Key was reused with a different request payload.",
                        "code": "IDEMPOTENCY_KEY_REUSE_MISMATCH",
                    },
                )
            return _build_hit_response(cached["response"])

        await cache_service.set(
            redis_key, {"status": "processing", "request_hash": payload_hash}, ttl_seconds=86400
        )

        try:
            response = await call_next(request)
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            if response.status_code < 500:
                headers_to_cache = {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower()
                    not in (
                        "date",
                        "keep-alive",
                        "server",
                        "x-request-id",
                        "x-trace-id",
                        "x-span-id",
                    )
                }
                cached_data = {
                    "status": "completed",
                    "request_hash": payload_hash,
                    "response": {
                        "status_code": response.status_code,
                        "headers": headers_to_cache,
                        "body": base64.b64encode(response_body).decode("utf-8"),
                    },
                }
                await cache_service.set(redis_key, cached_data, ttl_seconds=86400)

            headers = dict(response.headers)
            headers["X-Cache-Idempotency"] = "MISS"
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )
        except Exception:
            await cache_service.delete(redis_key)
            raise
