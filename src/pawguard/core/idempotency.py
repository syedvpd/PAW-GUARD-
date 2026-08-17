"""Middleware to handle API request idempotency using Redis caching."""

import base64
import hashlib
import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from pawguard.redis.client import _ensure_client, _NullRedis
from pawguard.services.cache_service import CacheService
from pawguard.core.security import parse_access_token_claims
from pawguard.core.constants import ACCESS_TOKEN_COOKIE_NAME

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


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Enforces API Idempotency via Idempotency-Key or X-Idempotency-Key headers.

    Checks mutating HTTP methods (POST, PUT, PATCH, DELETE). Ensures keys are bound to
    the authenticated user session and validated against identical request payloads to
    prevent duplicate transactions.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        idempotency_key = request.headers.get("idempotency-key") or request.headers.get("x-idempotency-key")
        if not idempotency_key:
            return await call_next(request)

        # Validate key length/format to prevent injection of excessively large values
        if len(idempotency_key) < 10 or len(idempotency_key) > 128:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Invalid Idempotency-Key format."}
            )

        redis = await _resolve_redis(request)
        if isinstance(redis, _NullRedis):
            # Fall back gracefully if Redis is down
            logger.warning("Idempotency requested but Redis is unreachable. Falling back to non-idempotent execution.")
            return await call_next(request)

        cache_service = CacheService(redis, namespace="idempotency")

        # 1. Read request body safely and replace the receive stream so downstream route can read it
        body_bytes = await request.body()
        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        request._receive = receive

        # 2. Extract authenticated user id securely from JWT claims to prevent key-hijacking across sessions
        user_id = "anonymous"
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
        else:
            token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
        if token:
            try:
                claims = parse_access_token_claims(token)
                user_id = str(claims.user_id)
            except Exception:
                pass

        # 3. Calculate fingerprint of the request payload (method, path, query, and body)
        query_str = str(request.query_params)
        payload_hash = hashlib.sha256(
            f"{request.method}:{request.url.path}:{query_str}:".encode("utf-8") + body_bytes
        ).hexdigest()

        redis_key = f"{idempotency_key}:{user_id}"

        # 4. Check cache status
        cached = await cache_service.get(redis_key)
        if cached:
            if cached.get("status") == "processing":
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "error": "Request is already in flight. Please retry later.",
                        "code": "IDEMPOTENCY_IN_FLIGHT"
                    }
                )
            
            # Verify payload hash matches to detect key reuse with different parameters
            if cached.get("request_hash") != payload_hash:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "Idempotency Key was reused with a different request payload.",
                        "code": "IDEMPOTENCY_KEY_REUSE_MISMATCH"
                    }
                )

            # Return cached response
            cached_resp = cached["response"]
            body_decoded = base64.b64decode(cached_resp["body"])
            headers = dict(cached_resp["headers"])
            headers["X-Cache-Idempotency"] = "HIT"
            return Response(
                content=body_decoded,
                status_code=cached_resp["status_code"],
                headers=headers,
                media_type=headers.get("content-type")
            )

        # 5. Lock key as processing
        await cache_service.set(
            redis_key, 
            {"status": "processing", "request_hash": payload_hash}, 
            ttl_seconds=86400  # 24 Hour expiry
        )

        try:
            response = await call_next(request)
            
            # 6. Capture response body chunks from Starlette's response iterator
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            # Only cache safe status codes (2xx, 3xx, 4xx, but NEVER 5xx Internal Server Errors)
            if response.status_code < 500:
                headers_to_cache = {
                    k: v for k, v in response.headers.items() 
                    if k.lower() not in ("date", "keep-alive", "server", "x-request-id", "x-trace-id", "x-span-id")
                }
                cached_data = {
                    "status": "completed",
                    "request_hash": payload_hash,
                    "response": {
                        "status_code": response.status_code,
                        "headers": headers_to_cache,
                        "body": base64.b64encode(response_body).decode("utf-8")
                    }
                }
                await cache_service.set(redis_key, cached_data, ttl_seconds=86400)

            # Return new response containing the consumed body content
            headers = dict(response.headers)
            headers["X-Cache-Idempotency"] = "MISS"
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type
            )
        except Exception:
            # Delete idempotency lock on exception so user can retry the request
            await cache_service.delete(redis_key)
            raise
