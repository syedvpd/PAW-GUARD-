"""Test fixtures: async engine, session, FastAPI client with dependency overrides."""

import os
import sys
from collections.abc import AsyncGenerator
from typing import Any

# Set default mock S3 credentials for local boto3 signature operations
os.environ.setdefault("AWS_ACCESS_KEY_ID", "mock_key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "mock_secret")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import base64
from unittest.mock import MagicMock
import boto3

original_boto3_client = boto3.client

def mock_boto3_client(service_name, *args, **kwargs):
    if service_name == "s3":
        mock_s3 = MagicMock()
        
        def get_object_mock(Bucket, Key, Range=None):
            key_str = str(Key).lower()
            if "pdf" in key_str:
                body_bytes = b"%PDF-1.4\n"
            elif "png" in key_str:
                body_bytes = base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            elif "jpg" in key_str or "jpeg" in key_str:
                body_bytes = b"\xff\xd8\xff\xe0"
            elif "webp" in key_str:
                body_bytes = b"RIFF\x00\x00\x00\x00WEBP"
            elif "mp4" in key_str:
                body_bytes = b"\x00\x00\x00\x18ftypmp42"
            else:
                body_bytes = b"dummy content"
            
            body_mock = MagicMock()
            body_mock.read.return_value = body_bytes
            return {"Body": body_mock}
            
        mock_s3.get_object.side_effect = get_object_mock
        mock_s3.head_object.return_value = {"ContentLength": 1024}
        mock_s3.generate_presigned_url.side_effect = lambda operation, Params, ExpiresIn=900: f"http://localhost/{Params.get('Bucket', 'bucket')}/{Params.get('Key', 'key')}"
        return mock_s3
    return original_boto3_client(service_name, *args, **kwargs)

boto3.client = mock_boto3_client

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

    async def scan_iter(self, match: str = ""):  # noqa: A002
        import fnmatch

        # Async generator to mirror redis-py's protocol — CacheService
        # consumes scan_iter with ``async for`` (see _NullRedis in
        # pawguard/redis/client.py for the production-side counterpart).
        for k in self._store:
            if fnmatch.fnmatch(k, match):
                yield k

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
    # Seed roles/permissions so DB-backed tests are self-contained. CI's fresh
    # database is only migrated (`alembic upgrade head`) and never seeded, yet
    # many integration tests look up seeded roles (e.g. super_admin) by name;
    # the production seeder runs in the app lifespan, which the ASGI test
    # client does not execute. reconcile_roles() is additive + idempotent, and
    # committing here makes the roles visible across the per-test rolled-back
    # transactions created by db_session.
    #
    # Do NOT create tables from ORM metadata here: the schema must come from
    # `alembic upgrade head`, never Base.metadata.create_all (it bypasses
    # alembic_version tracking and silently misses new columns).
    from scripts.seed_roles_and_permissions import reconcile_roles
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with async_sessionmaker(bind=eng, expire_on_commit=False)() as seed_session:
        await reconcile_roles(seed_session, verbose=False)
        await seed_session.commit()

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
