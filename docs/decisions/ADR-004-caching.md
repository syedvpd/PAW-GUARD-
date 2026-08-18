# ADR-004: Caching Strategy

## Status

Accepted

## Context

PawGuard requires caching for:
- RBAC permission lookups
- Dashboard statistics
- Real-time event publishing
- Rate limiting counters
- Agent location tracking

## Decision

Use **Redis** as the primary caching and real-time data store.

## Alternatives Considered

### Memcached
- **Pros**: Simple, fast, mature
- **Cons**: No data structures, no persistence, limited functionality
- **Verdict**: Rejected due to limited features

### In-memory (Python dict)
- **Pros**: Zero latency, no external dependency
- **Cons**: Not shared across workers, lost on restart, no real-time
- **Verdict**: Rejected for multi-worker deployment

### Database-only caching
- **Pros**: Single data store, ACID compliance
- **Cons**: Slower than Redis, higher latency
- **Verdict**: Rejected for performance-critical operations

### Redis Cluster
- **Pros**: High availability, horizontal scaling
- **Cons**: More complex setup, higher cost
- **Verdict**: Rejected for current scale (single Redis sufficient)

## Consequences

### Positive
- Sub-millisecond latency
- Rich data structures (sets, sorted sets, geo)
- Built-in expiration (TTL)
- Pub/Sub for real-time events
- Atomic operations
- Persistence options

### Negative
- Additional infrastructure dependency
- Memory limitations
- Data consistency challenges

## Use Cases

### RBAC Permission Caching
```python
# Cache key: rbac:roles:role1:role2
# TTL: 300 seconds
# Invalidated on role/permission changes
```

### Dashboard Statistics
```python
# Keys: pawguard:hero_stats, pawguard:transparency_stats
# Cached dashboard aggregation results
# Invalidated on data changes
```

### Rate Limiting
```python
# Key: rate_limit:{prefix}:{user_id}:{window_bucket}
# Atomic INCR + EXPIRE
# Auto-expiration after window
```

### Agent Location Tracking
```python
# GEO commands for spatial queries
# Heartbeat TTL for liveness detection
# GEORADIUS for nearby agent suggestions
```

### Real-time Events
```python
# Pub/Sub channels: dispatch:events
# Used for real-time dispatch updates
# Best-effort delivery (no persistence)
```

### Session Storage
```python
# Sessions stored in PostgreSQL (not Redis)
# Redis used only for caching and real-time
# Session validation requires DB lookup
```

## Cache Invalidation Strategy

### RBAC Cache
- Invalidated on role create/update/delete
- Namespace-based deletion: `rbac:roles:*`
- TTL fallback: 300 seconds

### Dashboard Cache
- Invalidated on data mutations
- Specific key deletion (not pattern-based)
- Keys: `cache:dashboard:{module}`

### Idempotency Keys
- TTL-based expiration (24 hours)
- Automatic cleanup

## Configuration

```bash
REDIS_URL=redis://localhost:6379/0
```

## Monitoring

- Redis ping in health checks (`/ready` endpoint)
- Connection pooling via `redis-py`
- Structured logging for cache operations
