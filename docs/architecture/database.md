# Database Architecture

Scope: Schema design, ORM patterns, migrations, read/write splitting, sharding, and data integrity.

---

## 1. Database Engine

### PostgreSQL Configuration

| Setting | Value | Source |
|---------|-------|--------|
| Driver | asyncpg (async) | `pyproject.toml:13` |
| Pool Size | 20 connections | `config.py:84` |
| Max Overflow | 10 connections | `config.py:85` |
| Pool Recycle | 1800 seconds | `db/session.py:34` |
| Pool Timeout | 30 seconds | `db/session.py:35` |
| Pool Pre-ping | True | `db/session.py:33` |
| Statement Cache | 0 (disabled) | `db/session.py:36` |
| Echo | Configurable | `config.py:86` |

### Connection Pool Monitoring

The application collects real-time pool metrics exposed via `/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `db_pool_size` | Gauge | configured pool size |
| `db_pool_checked_in` | Gauge | connections returned to pool |
| `db_pool_checked_out` | Gauge | active connections |
| `db_pool_overflow` | Gauge | overflow connections |

Source: `src/pawguard/db/session.py:100-118`

---

## 2. Read/Write Splitting

The application implements automatic read/write splitting at the session dependency level:

### Strategy

| Request Method | Database | Use Case |
|---------------|----------|----------|
| `GET` | Read Replica | All read-only operations |
| `POST`, `PUT`, `PATCH`, `DELETE` | Primary | All write operations |

### Implementation

```python
# From db/session.py
async def get_db(request: Request = None) -> AsyncGenerator[AsyncSession]:
    if request is not None and request.method == "GET":
        async with AsyncReplicaSessionLocal() as session:
            # Read replica for GET requests
            ...
    else:
        async with AsyncSessionLocal() as session:
            # Primary for all mutations
            ...
```

### Replica Configuration

| Setting | Source |
|---------|--------|
| Primary URL | `DATABASE_URL` |
| Replica URL | `DATABASE_REPLICA_URL` (falls back to primary) |

When `DATABASE_REPLICA_URL` is unset, both primary and replica engines point to the same database. This allows the architecture to be ready for horizontal read scaling without code changes.

Source: `src/pawguard/db/session.py:46-64`

---

## 3. ORM Base and Naming Conventions

### Declarative Base

```python
# From db/base.py
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

The explicit naming convention ensures:
- Deterministic Alembic migration generation
- Predictable constraint names for raw SQL references
- Consistent naming across all modules

Source: `src/pawguard/db/base.py:1-20`

---

## 4. Reusable Mixins

### UUID Primary Key

```python
class UUIDPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
```

All tables use UUID primary keys generated server-side via `gen_random_uuid()`.

### Timestamps

```python
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
```

### Soft Delete

```python
class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
```

Operational records are never hard-deleted. The `deleted_at` timestamp marks records as deleted while preserving them for audit and recovery.

### Audit Trail

```python
class AuditMixin:
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```

Source: `src/pawguard/db/mixins.py:1-64`

---

## 5. Query Performance Monitoring

### Slow Query Detection

The application instruments all database queries via SQLAlchemy event listeners:

```python
# From db/session.py
@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(...):
    elapsed = (time.perf_counter() - start_times.pop()) * 1000
    observe_histogram("db_query_duration_ms", elapsed, {"type": stmt_clean})
    increment_counter("db_queries_total", {"type": stmt_clean})
    if elapsed > 100.0:
        increment_counter("db_slow_queries_total", {"type": stmt_clean})
```

### Metrics Collected

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `db_query_duration_ms` | Histogram | `type` (SELECT/INSERT/UPDATE/DELETE) | Query latency distribution |
| `db_queries_total` | Counter | `type` | Total query count by type |
| `db_slow_queries_total` | Counter | `type` | Queries exceeding 100ms |

Source: `src/pawguard/db/session.py:67-98`

---

## 6. Database Sharding

A shard registry pattern is implemented for horizontal database scaling:

### ShardRegistry

```python
class ShardRegistry:
    def register_shard(self, shard_key: str, database_url: str, **engine_kwargs) -> None:
        """Register a database engine for a specific shard key."""
    
    def get_sessionmaker(self, shard_key: str) -> async_sessionmaker[AsyncSession] | None:
        """Get session maker for a shard."""
```

### ShardedSessionManager

```python
class ShardedSessionManager:
    def get_session_for_shard(self, shard_key: str) -> AsyncSession:
        """Resolve session for the specified shard."""
    
    def get_shard_key_for_shelter(self, shelter_id: uuid.UUID) -> str:
        """Route by shelter ID prefix (consistent hashing)."""
```

### Routing Strategy

Shard assignment uses UUID prefix-based routing:
- IDs starting with `0`, `1`, `2` -> `shard_east`
- All others -> `shard_west`

This infrastructure is in place for future multi-region deployments.

Source: `src/pawguard/db/sharding.py:1-51`

---

## 7. Audit Stamps

The application automatically tracks who created and last updated every row via the `before_flush` event listener:

```python
# From db/audit.py (imported as side effect in session.py)
import pawguard.db.audit  # noqa: F401
```

This listener fires before every flush and stamps `created_by` and `updated_by` fields from the request context.

---

## 8. Alembic Migrations

### Configuration

| Setting | Value |
|---------|-------|
| Config File | `alembic.ini` |
| Migration Directory | `alembic/` |
| Script Template | `alembic/script.py.mako` |

### Migration Conventions

1. Every schema change requires a migration
2. Migrations must be idempotent and reversible
3. Migrations must preserve data integrity
4. Foreign key constraints are explicitly defined
5. Indexes are created concurrently when possible
6. Never modify production data manually in migrations

### Migration Lifecycle

```
1. Create migration: alembic revision --autogenerate -m "description"
2. Review generated SQL
3. Apply locally: alembic upgrade head
4. Test rollback: alembic downgrade -1
5. Deploy to staging/production
```

---

## 9. Data Integrity Patterns

### Foreign Key Constraints

All inter-table relationships use explicit foreign keys with appropriate `ON DELETE` behavior:

| Behavior | Use Case |
|----------|----------|
| `CASCADE` | Child records that must not outlive parent |
| `SET NULL` | Optional references (audit fields) |
| `RESTRICT` | References that must be explicitly removed |

### Unique Constraints

Composite unique constraints enforce business invariants at the database level (e.g., one active session per device, one MFA device per user).

### Check Constraints

Enum-like columns use `String` with application-level validation via Pydantic, rather than PostgreSQL ENUM types, to simplify migrations.

### JSONB Columns

Flexible metadata is stored in JSONB columns (e.g., `outbox_events.payload`, `auth_audit_logs.event_metadata`). The application ensures JSON-serializable values via the `_jsonable()` helper.

Source: `src/pawguard/services/audit_service.py:15-34`

---

## 10. Connection Lifecycle

### Session Management

```python
async def get_db(request: Request = None) -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except Exception:
            if session.in_transaction():
                await session.rollback()
            raise
```

Key properties:
- Sessions are auto-committed on success
- Sessions are auto-rolled-back on exception
- `expire_on_commit=False` prevents lazy loading after commit
- `autoflush=False` gives explicit control over flush timing

### Engine Disposal

The application disposes of the database engine on shutdown:

```python
# From main.py lifespan
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    logger.info("application_startup")
    await _seed_roles()
    yield
    await engine.dispose()
    logger.info("application_shutdown")
```

Source: `src/pawguard/main.py:65-72`
