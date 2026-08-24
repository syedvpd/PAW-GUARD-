import asyncio

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.resilience import CircuitBreaker, CircuitBreakerOpenException, retry_with_backoff
from pawguard.db.session import get_db, replica_engine

# --- 1. Resilience Tests ---


@pytest.mark.asyncio
async def test_retry_with_backoff_success() -> None:
    call_count = 0

    @retry_with_backoff(exceptions=(ValueError,), max_retries=3, initial_delay=0.01)
    async def transient_fail_function() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Transient error")
        return "success"

    res = await transient_fail_function()
    assert res == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_with_backoff_permanent_failure() -> None:
    call_count = 0

    @retry_with_backoff(exceptions=(ValueError,), max_retries=2, initial_delay=0.01)
    async def permanent_fail_function() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("Permanent error")

    with pytest.raises(ValueError, match="Permanent error"):
        await permanent_fail_function()
    assert call_count == 3  # Initial attempt + 2 retries


@pytest.mark.asyncio
async def test_circuit_breaker_transitions() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
    call_count = 0

    @breaker
    async def test_func(should_fail: bool) -> str:
        nonlocal call_count
        call_count += 1
        if should_fail:
            raise ValueError("Fail")
        return "OK"

    # First attempt: failure recorded
    with pytest.raises(ValueError):
        await test_func(should_fail=True)
    assert breaker.failure_count == 1
    assert breaker.state.value == "closed"

    # Second attempt: failure threshold reached, trips to OPEN
    with pytest.raises(ValueError):
        await test_func(should_fail=True)
    assert breaker.failure_count == 2
    assert breaker.state.value == "open"

    # Third attempt: OPEN circuit should fail fast
    with pytest.raises(CircuitBreakerOpenException):
        await test_func(should_fail=False)

    # Await recovery timeout to allow HALF-OPEN transition
    await asyncio.sleep(0.06)

    # Next attempt succeeds: state transitions back to CLOSED
    res = await test_func(should_fail=False)
    assert res == "OK"
    assert breaker.state.value == "closed"
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_sync_circuit_breaker_transitions() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
    call_count = 0

    @breaker
    def test_sync_func(should_fail: bool) -> str:
        nonlocal call_count
        call_count += 1
        if should_fail:
            raise ValueError("Fail")
        return "OK"

    # First attempt: failure recorded
    with pytest.raises(ValueError):
        test_sync_func(should_fail=True)
    assert breaker.failure_count == 1
    assert breaker.state.value == "closed"

    # Second attempt: failure threshold reached, trips to OPEN
    with pytest.raises(ValueError):
        test_sync_func(should_fail=True)
    assert breaker.failure_count == 2
    assert breaker.state.value == "open"

    # Third attempt: OPEN circuit should fail fast
    with pytest.raises(CircuitBreakerOpenException):
        test_sync_func(should_fail=False)

    # Await recovery timeout to allow HALF-OPEN transition
    await asyncio.sleep(0.06)

    # Next attempt succeeds: state transitions back to CLOSED
    res = test_sync_func(should_fail=False)
    assert res == "OK"
    assert breaker.state.value == "closed"
    assert breaker.failure_count == 0


# --- 2. Database Read/Write Splitting Tests ---


@pytest.fixture
def splitting_app() -> FastAPI:
    app = FastAPI()

    @app.get("/test-read")
    async def read_endpoint(session: AsyncSession = Depends(get_db)) -> dict[str, str]:
        # Expose the database engine name bound to this session
        is_replica = session.bind == replica_engine
        return {"bind": "replica" if is_replica else "primary"}

    @app.post("/test-write")
    async def write_endpoint(session: AsyncSession = Depends(get_db)) -> dict[str, str]:
        is_replica = session.bind == replica_engine
        return {"bind": "replica" if is_replica else "primary"}

    return app


@pytest.mark.asyncio
async def test_read_write_splitting_routing(splitting_app: FastAPI) -> None:
    transport = ASGITransport(app=splitting_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET request should route to the Read Replica engine
        r1 = await client.get("/test-read")
        assert r1.status_code == 200
        assert r1.json()["bind"] == "replica"

        # POST request should route to the Primary/Write database engine
        r2 = await client.post("/test-write")
        assert r2.status_code == 200
        assert r2.json()["bind"] == "primary"
