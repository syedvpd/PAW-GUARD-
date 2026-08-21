"""E2E Test Configuration & Fixtures."""
# ruff: noqa: E402

import os

os.environ.setdefault("AWS_ACCESS_KEY_ID", "mock_key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "mock_secret")
os.environ["ENVIRONMENT"] = "test"

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import boto3

original_boto3_client = boto3.client


def mock_boto3_client(service_name, *args, **kwargs):
    if service_name == "s3":
        mock_s3 = MagicMock()

        def get_object_mock(Bucket, Key, Range=None):
            body_mock = MagicMock()
            body_mock.read.return_value = b"dummy content"
            return {"Body": body_mock}

        mock_s3.get_object.side_effect = get_object_mock
        mock_s3.head_object.return_value = {"ContentLength": 1024}
        mock_s3.generate_presigned_url.side_effect = lambda operation, Params, ExpiresIn=900: (
            f"http://localhost/{Params.get('Bucket', 'bucket')}/{Params.get('Key', 'key')}"
        )
        return mock_s3
    return original_boto3_client(service_name, *args, **kwargs)


boto3.client = mock_boto3_client

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from pawguard.core.config import get_settings
from pawguard.db.session import get_db
from pawguard.main import create_app
from pawguard.redis.client import get_redis
from pawguard.workers.pool import get_arq_pool


class FakeRedis:
    def __init__(self):
        self._store = {}
        self._expiry = {}

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, ex=None):
        self._store[key] = value

    async def incr(self, key):
        val = int(self._store.get(key, 0)) + 1
        self._store[key] = val
        return val

    async def expire(self, key, _time):
        pass

    async def delete(self, key):
        self._store.pop(key, None)

    async def scan_iter(self, match=""):
        import fnmatch

        for k in self._store:
            if fnmatch.fnmatch(k, match):
                yield k

    async def ping(self):
        return True


class FakeArqPool:
    async def enqueue_job(self, _name, **kwargs):
        pass


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    settings = get_settings()
    test_url = settings.database_url_frontend or settings.database_url
    eng = create_async_engine(
        test_url,
        echo=False,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    from scripts.seed_roles_and_permissions import reconcile_roles
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with async_sessionmaker(bind=eng, expire_on_commit=False)() as seed_session:
        await reconcile_roles(seed_session, verbose=False)
        await seed_session.commit()

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
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
async def client(db_session: AsyncSession, fake_redis: FakeRedis) -> AsyncGenerator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_arq_pool] = lambda: FakeArqPool()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def setup(client: AsyncClient, db_session: AsyncSession):
    """Create all prerequisite data and return the TEST state object."""
    from tests.e2e.factories import TEST, setup_all_prerequisites

    await setup_all_prerequisites(client, db_session)
    return TEST
