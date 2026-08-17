"""Unit tests for the IdempotencyMiddleware."""

import asyncio
import uuid
import pytest
from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from pawguard.core.idempotency import IdempotencyMiddleware
from pawguard.redis.client import get_redis
from tests.conftest import FakeRedis

# A mock counter to track execution attempts of mutating endpoints
MUTATE_EXECUTION_COUNT = 0


@pytest.fixture(autouse=True)
def reset_mutate_count():
    global MUTATE_EXECUTION_COUNT
    MUTATE_EXECUTION_COUNT = 0


@pytest.fixture
def test_app(fake_redis) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_redis] = lambda: fake_redis

    app.add_middleware(IdempotencyMiddleware)

    @app.post("/test-mutate")
    async def mutate_endpoint(payload: dict):
        global MUTATE_EXECUTION_COUNT
        MUTATE_EXECUTION_COUNT += 1
        
        # If payload specifies raise_error, raise exception
        if payload.get("raise_error"):
            raise ValueError("Intentional execution failure")
            
        return {"attempt": MUTATE_EXECUTION_COUNT, "data": payload.get("value")}

    @app.get("/test-query")
    async def query_endpoint():
        global MUTATE_EXECUTION_COUNT
        MUTATE_EXECUTION_COUNT += 1
        return {"attempt": MUTATE_EXECUTION_COUNT}

    return app


@pytest.mark.asyncio
async def test_idempotency_disabled_for_get_requests(test_app):
    """GET requests must ignore idempotency headers and execute normally without caching."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Idempotency-Key": "test-key-123456"}

        r1 = await client.get("/test-query", headers=headers)
        assert r1.status_code == 200
        assert r1.json()["attempt"] == 1
        assert "X-Cache-Idempotency" not in r1.headers

        # Subsequent requests execute again
        r2 = await client.get("/test-query", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["attempt"] == 2


@pytest.mark.asyncio
async def test_idempotency_disabled_when_header_missing(test_app):
    """Mutating requests without an idempotency key header must execute normally without caching."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/test-mutate", json={"value": "a"})
        assert r1.status_code == 200
        assert r1.json()["attempt"] == 1
        assert "X-Cache-Idempotency" not in r1.headers

        r2 = await client.post("/test-mutate", json={"value": "a"})
        assert r2.status_code == 200
        assert r2.json()["attempt"] == 2


@pytest.mark.asyncio
async def test_idempotency_caching_and_hit_return(test_app):
    """Mutating requests with an identical idempotency key must execute once, cache the response, and return hits on duplicate requests."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Idempotency-Key": "valid-idempotency-key-string"}
        payload = {"value": "secure-donation-amount"}

        # Attempt 1: MISS (Executes the route handler)
        r1 = await client.post("/test-mutate", json=payload, headers=headers)
        assert r1.status_code == 200
        assert r1.json()["attempt"] == 1
        assert r1.headers.get("X-Cache-Idempotency") == "MISS"

        # Attempt 2: HIT (Returns cached response from Redis)
        r2 = await client.post("/test-mutate", json=payload, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["attempt"] == 1  # Verify attempt counter was not incremented
        assert r2.headers.get("X-Cache-Idempotency") == "HIT"


@pytest.mark.asyncio
async def test_idempotency_key_reuse_mismatch(test_app):
    """Reusing the same key with different payloads must be rejected with 400 Bad Request."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Idempotency-Key": "valid-idempotency-key-string"}

        # Initial request
        await client.post("/test-mutate", json={"value": "donation-10"}, headers=headers)

        # Reused key but payload is different
        r2 = await client.post("/test-mutate", json={"value": "donation-20"}, headers=headers)
        assert r2.status_code == 400
        assert r2.json()["code"] == "IDEMPOTENCY_KEY_REUSE_MISMATCH"


@pytest.mark.asyncio
async def test_idempotency_in_flight_processing(test_app, fake_redis):
    """Reusing a key that is currently processing must return 409 Conflict."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Idempotency-Key": "valid-idempotency-key-string"}

        # Manually lock the key in FakeRedis to simulate in-flight execution
        # Key namespace is 'idempotency:{key}:{user_id}' (using anonymous for testing)
        await fake_redis.set("idempotency:valid-idempotency-key-string:anonymous", '{"status": "processing", "request_hash": "dummy"}')

        r = await client.post("/test-mutate", json={"value": "test"}, headers=headers)
        assert r.status_code == 409
        assert r.json()["code"] == "IDEMPOTENCY_IN_FLIGHT"


@pytest.mark.asyncio
async def test_idempotency_lock_cleared_on_exception(test_app, fake_redis):
    """If the route execution raises an exception, the idempotency lock must be deleted from Redis to allow future retries."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Idempotency-Key": "valid-idempotency-key-string"}
        payload = {"value": "error-value", "raise_error": True}

        # Request raises ValueError inside route
        with pytest.raises(ValueError, match="Intentional execution failure"):
            await client.post("/test-mutate", json=payload, headers=headers)

        # Lock key in Redis namespace must be deleted
        redis_val = await fake_redis.get("idempotency:valid-idempotency-key-string:anonymous")
        assert redis_val is None
