"""Test fixtures: async engine, session, FastAPI client with dependency overrides."""

import sys
from collections.abc import AsyncGenerator
from typing import Any

# Ensure UTF-8 for structlog's ConsoleRenderer (uses Unicode box-drawing chars).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from pawguard.core.config import get_settings
from pawguard.db.session import get_db
from pawguard.main import create_app
from pawguard.redis.client import get_redis
from pawguard.workers.pool import get_arq_pool


class FakeRedis:
    """In-memory Redis mock for testing (supports only what the app uses)."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}

    async def get(self, key: str) -> Any | None:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:  # noqa: A002
        self._store[key] = value

    async def incr(self, key: str) -> int:
        val = int(self._store.get(key, 0))
        val += 1
        self._store[key] = val
        return val

    async def expire(self, key: str, _time: int) -> None:
        pass

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def scan_iter(self, match: str = "") -> list[str]:  # noqa: A002
        import fnmatch

        return [k for k in self._store if fnmatch.fnmatch(k, match)]

    async def ping(self) -> bool:
        return True


class FakeArqPool:
    """In-memory ARQ pool mock — jobs are silently discarded."""

    async def enqueue_job(self, _name: str, **kwargs: Any) -> None:  # noqa: A002
        pass


@pytest_asyncio.fixture(scope="module")
async def engine() -> AsyncGenerator[AsyncEngine]:
    settings = get_settings()
    test_url = settings.database_url_frontend or settings.database_url
    eng = create_async_engine(
        test_url,
        echo=False,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    # Schema must already be migrated (`alembic upgrade head`) before running
    # these tests. Do NOT create tables from ORM metadata here: this database
    # is shared with local dev (no separate test DB is configured), and
    # Base.metadata.create_all only creates missing tables - it never adds
    # new columns to existing ones, and it bypasses alembic_version tracking
    # entirely. That previously desynced alembic_version from the real
    # physical schema and left new columns (e.g. inventory_items.unit_cost)
    # silently missing. If a required table doesn't exist, the fix is to add
    # or run a migration, not to route around Alembic here.
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(
    engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession]:
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()


@pytest_asyncio.fixture
async def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    fake_redis: FakeRedis,
) -> AsyncGenerator[AsyncClient]:
    app = create_app()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_arq_pool] = lambda: FakeArqPool()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as ac:
        yield ac

    app.dependency_overrides.clear()
