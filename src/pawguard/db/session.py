import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Registers the before_flush audit-stamp listener as a side effect of import.
import pawguard.db.audit  # noqa: F401
from pawguard.core.config import get_settings
from pawguard.core.metrics import (
    increment_counter,
    observe_histogram,
    set_gauge,
)

_settings = get_settings()


def _get_engine_kwargs(url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "echo": _settings.database_echo,
    }
    if "sqlite" not in url:
        kwargs.update(
            {
                "pool_size": _settings.database_pool_size,
                "max_overflow": _settings.database_max_overflow,
                "pool_pre_ping": True,
                "pool_recycle": 1800,
                "pool_timeout": 15,
                "connect_args": {"statement_cache_size": 0},
            }
        )
    return kwargs


engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    **_get_engine_kwargs(_settings.database_url),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

replica_url = _settings.database_replica_url or _settings.database_url

replica_engine: AsyncEngine = create_async_engine(
    replica_url,
    **_get_engine_kwargs(replica_url),
)

AsyncReplicaSessionLocal = async_sessionmaker(
    bind=replica_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(
    conn: Connection,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())


@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(
    conn: Connection,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    start_times = conn.info.get("query_start_time")
    if start_times:
        elapsed = (time.perf_counter() - start_times.pop()) * 1000
        stmt_clean = statement.strip().split()[0].upper() if statement.strip() else "OTHER"
        if stmt_clean not in (
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "COMMIT",
            "ROLLBACK",
            "BEGIN",
        ):
            stmt_clean = "OTHER"
        observe_histogram("db_query_duration_ms", elapsed, {"type": stmt_clean})
        increment_counter("db_queries_total", {"type": stmt_clean})
        if elapsed > 100.0:
            increment_counter("db_slow_queries_total", {"type": stmt_clean})


def collect_db_pool_metrics() -> dict[str, int]:
    """Collect current SQLAlchemy connection pool telemetry."""
    pool = engine.pool
    size = pool.size() if hasattr(pool, "size") else 0
    checked_in = pool.checkedin() if hasattr(pool, "checkedin") else 0
    checked_out = pool.checkedout() if hasattr(pool, "checkedout") else 0
    overflow = pool.overflow() if hasattr(pool, "overflow") else 0

    set_gauge("db_pool_size", float(size))
    set_gauge("db_pool_checked_in", float(checked_in))
    set_gauge("db_pool_checked_out", float(checked_out))
    set_gauge("db_pool_overflow", float(overflow))

    return {
        "size": size,
        "checked_in": checked_in,
        "checked_out": checked_out,
        "overflow": overflow,
    }


async def get_db(request: Request = None) -> AsyncGenerator[AsyncSession]:
    if request is not None and request.method == "GET":
        async with AsyncReplicaSessionLocal() as session:
            try:
                yield session
                if session.in_transaction():
                    await session.commit()
            except Exception:
                if session.in_transaction():
                    await session.rollback()
                raise
    else:
        async with AsyncSessionLocal() as session:
            try:
                yield session
                if session.in_transaction():
                    await session.commit()
            except Exception:
                if session.in_transaction():
                    await session.rollback()
                raise


async def get_master_db() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except Exception:
            if session.in_transaction():
                await session.rollback()
            raise
