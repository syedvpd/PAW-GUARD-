# ADR-002: Database

## Status

Accepted

## Context

PawGuard requires a relational database for:
- Complex relationships (users, roles, rescues, dogs, adoptions)
- ACID compliance for financial and operational data
- JSON support for flexible metadata
- Full-text search capabilities
- UUID primary keys

## Decision

Use **PostgreSQL** with **Supabase** as the managed service provider.

## Alternatives Considered

### MySQL
- **Pros**: Popular, well-understood, good performance
- **Cons**: Limited JSON support, no native UUID, less mature full-text search
- **Verdict**: Rejected due to JSON and UUID limitations

### SQLite
- **Pros**: Zero-config, embedded, simple
- **Cons**: No concurrent writes, limited scalability, no network access
- **Verdict**: Rejected for production use (used only for testing)

### MongoDB
- **Pros**: Flexible schema, horizontal scaling
- **Cons**: No ACID transactions, complex relationships harder, less mature
- **Verdict**: Rejected due to relational data requirements

### AWS Aurora
- **Pros**: Managed PostgreSQL, high availability
- **Cons**: Higher cost, vendor lock-in, more complex setup
- **Verdict**: Rejected in favor of Supabase for cost and simplicity

## Consequences

### Positive
- Full ACID compliance
- Native JSON/JSONB support
- UUID primary keys
- Full-text search
- Mature replication and backup
- Supabase provides managed hosting with built-in auth, storage, real-time

### Negative
- Requires connection pooling (asyncpg)
- More complex setup than SQLite
- Supabase vendor dependency

## Implementation Notes

### Connection Configuration
```python
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

### SQLAlchemy Async
- Uses `asyncpg` driver for async operations
- `SQLAlchemy[asyncio]` for async ORM support
- Connection pooling configured via environment variables

### Alembic Migrations
- Version-controlled schema changes
- Run on application startup via `_seed_roles()`
- Idempotent reconciliation for roles/permissions

### Supabase Features Used
- PostgreSQL database hosting
- Row-level security (optional)
- Real-time subscriptions (for dispatch events)
- Storage for media files
