# Caching Strategy

Scope: Redis client architecture, CacheService, RBAC caching, idempotency, distributed locks, and graceful degradation.

---

## 1. Redis Client Architecture

### Connection Design

The Redis client is implemented as a lazy-initializing singleton with graceful degradation:

```
Application Start
    |
    v
[1] Attempt Redis connection (0.1s timeout)
    |
    +--- Success ---> Use real Redis client
    |
    +--- Failure ---> Use _NullRedis (all operations no-op)
```

### _NullRedis Pattern

When Redis is unreachable, the application continues operating with degraded functionality:

| Feature | Behavior Without Redis |
|---------|----------------------|
| Caching | Cache misses (no errors) |
| Rate Limiting | Disabled (all requests allowed) |
| Idempotency | Disabled (requests processed normally) |
| RBAC Cache | Database queried on every permission check |
| Job Queue | Jobs dropped with warning log |

```python
# From redis/client.py
class _NullRedis:
    async def get(self, key: str) -> None:
        return None
    async def set(self, key: str, value: Any, **kwargs) -> Any:
        return None
    async def ping(self) -> bool:
        return False
    async def scan_iter(self, match: str = "", count: int | None = None):
        return
        yield  # marks as async generator
```

Source: `src/pawguard/redis/client.py:30-78`

### Client Resolution

```python
async def _ensure_client() -> RedisClient:
    global _pool, _client, _redis_available
    if _client is not None:
        return _client
    if _redis_available is False:
        _client = cast(RedisClient, _NullRedis())
        return _client
    try:
        test_client = Redis.from_url(
            _settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.1,
            socket_timeout=0.1,
            retry_on_timeout=False,
        )
        await test_client.ping()
        _redis_available = True
        _client = cast(RedisClient, test_client)
    except Exception:
        _redis_available = False
        _client = cast(RedisClient, _NullRedis())
    return _client
```

### FastAPI Dependency

```python
async def get_redis() -> AsyncGenerator[RedisClient]:
    yield await _ensure_client()
```

Source: `src/pawguard/redis/client.py:83-108`

---

## 2. CacheService

### Design Principles

1. **Namespaced isolation** - Every cache entry is prefixed with a namespace
2. **Mandatory TTL** - No unbounded caching; every entry expires
3. **Metrics instrumentation** - Every operation records latency and hit/miss counts
4. **Graceful error handling** - Redis failures propagate metrics but do not crash requests

### Interface

| Method | Parameters | Description |
|--------|-----------|-------------|
| `get(key)` | Cache key | Retrieve cached value |
| `set(key, value, ttl_seconds)` | Key, value, TTL (default 300s) | Store value with expiry |
| `delete(key)` | Cache key | Remove single entry |
| `delete_prefix(prefix)` | Key prefix | Remove all entries matching prefix |
| `acquire_lock(key, token, expire_ms)` | Lock key, unique token, TTL | Acquire distributed lock |
| `release_lock(key, token)` | Lock key, ownership token | Release lock atomically |

### Namespaces

| Namespace | Purpose | TTL |
|-----------|---------|-----|
| `rbac` | Role-to-permission mappings | 300 seconds |
| `idempotency` | Request deduplication | 86400 seconds (24h) |
| `pawguard` | General cache | 300 seconds (default) |

### Metrics

Every CacheService operation records:

| Metric | Labels | Description |
|--------|--------|-------------|
| `redis_operation_duration_ms` | `op`, `namespace` | Operation latency |
| `redis_cache_hits_total` | `namespace` | Cache hit count |
| `redis_cache_misses_total` | `namespace` | Cache miss count |
| `redis_operations_total` | `op`, `namespace`, `status` | Operation outcome |

Source: `src/pawguard/services/cache_service.py:1-125`

---

## 3. RBAC Permission Caching

### Problem

Permission checks require joining `users -> roles -> role_permissions -> permissions`. Without caching, every authenticated request triggers this multi-table query.

### Solution

Permission codes are cached per role-name combination:

```
Key:    rbac:roles:{sorted_role_names joined by :}
Value:  JSON array of permission code strings
TTL:    300 seconds
```

### Cache Flow

```
RequirePermission("rescue:create")
    |
    v
[1] Check if user has admin role (super_admin, system:admin)
    |--- Yes --> Grant access (no DB query)
    |
    v
[2] Build cache key: "rbac:roles:rescue_admin:volunteer"
    |
    v
[3] Check Redis for cached permissions
    |--- Hit --> Use cached set
    |--- Miss --> Query database, cache result (300s TTL)
    |
    v
[4] Check if required permission is in set
    |--- Yes --> Grant access
    |--- No --> Raise InsufficientPermissionsError
```

### Cache Invalidation

Permission cache is invalidated on any role mutation:

```python
# From modules/auth/service.py (AdminService)
async def _invalidate_rbac_cache(self) -> None:
    if self._redis is None:
        return
    await CacheService(self._redis, namespace="rbac").delete_prefix("roles")
```

This is called after:
- Role creation
- Role update
- Role deletion
- Permission assignment changes

Source: `src/pawguard/modules/auth/rbac.py:55-84`

---

## 4. Idempotency Caching

### Purpose

Prevents duplicate processing of mutating requests (POST, PUT, PATCH, DELETE) when clients retry.

### Cache Structure

```
Key:    idempotency:{idempotency_key}:{user_id}
Value:  {
    "status": "processing" | "completed",
    "request_hash": "sha256 of method:path:query:body",
    "response": {
        "status_code": 201,
        "headers": {...},
        "body": "base64 encoded"
    }
}
TTL:    86400 seconds (24 hours)
```

### Flow

```
Mutating Request + Idempotency-Key header
    |
    v
[1] Validate key format (10-128 chars)
    |
    v
[2] Extract user_id from JWT
    |
    v
[3] Compute payload hash (method + path + query + body)
    |
    v
[4] Check Redis for existing key
    |--- "processing" --> Return 409 CONFLICT
    |--- "completed" + hash match --> Return cached response (HIT)
    |--- "completed" + hash mismatch --> Return 400 KEY_REUSE_MISMATCH
    |--- Not found --> Continue
    |
    v
[5] Store "processing" status with hash
    |
    v
[6] Execute request handler
    |
    v
[7] Store "completed" status with response (cache 2xx/3xx/4xx, never 5xx)
    |
    v
[8] Return response with X-Cache-Idempotency: MISS
```

### Safety Rules

- 5xx responses are never cached (allows server-side retry)
- In-flight requests return 409 (prevents concurrent duplicate processing)
- Payload hash mismatch returns 400 (prevents key reuse across different requests)
- Lock is deleted on exception (allows retry after failure)

Source: `src/pawguard/core/idempotency.py:40-180`

---

## 5. Distributed Locks

### Use Case

Prevents concurrent execution of critical operations (e.g., sponsorship charges, outbox processing).

### Implementation

```python
# Acquire lock
acquired = await cache_service.acquire_lock(
    lock_key="sponsorship:charge:run",
    token=str(uuid.uuid4()),  # unique owner token
    expire_ms=10000  # 10 second auto-expiry
)

# Release lock (atomic Lua script)
released = await cache_service.release_lock(
    lock_key="sponsorship:charge:run",
    token=acquired_token
)
```

### Lua Script for Atomic Release

```lua
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
```

This ensures only the lock owner can release it, preventing accidental release by a different process.

### Safety Features

- **Auto-expiry** - Locks expire after configured TTL (prevents deadlocks)
- **Owner verification** - Only the lock holder can release
- **NullRedis fallback** - When Redis is unavailable, locks are not acquired (fail-closed)

Source: `src/pawguard/services/cache_service.py:74-124`

---

## 6. Cache Invalidation Strategy

### Invalidation Patterns

| Pattern | When | Example |
|---------|------|---------|
| TTL Expiry | Automatic | All cached values expire after TTL |
| Prefix Delete | On mutation | RBAC cache cleared on role changes |
| Single Key Delete | On specific mutation | Invalidate specific user cache |
| Never Cached | Security | Passwords, tokens, permissions without invalidation |

### CACHE CONTRACT (from AGENTS.md)

1. Only cache data that benefits performance
2. Never cache security decisions without invalidation
3. Never cache transactional writes
4. Always define cache invalidation
5. Permissions are never cached without invalidation

---

## 7. Metrics and Monitoring

### Redis Operation Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `redis_operation_duration_ms` | Histogram | `op`, `namespace` | Operation latency |
| `redis_cache_hits_total` | Counter | `namespace` | Cache hit count |
| `redis_cache_misses_total` | Counter | `namespace` | Cache miss count |
| `redis_operations_total` | Counter | `op`, `namespace`, `status` | Operation outcome |

### Operation Labels

| `op` Value | Description |
|------------|-------------|
| `get` | Read from cache |
| `set` | Write to cache |
| `delete` | Remove single key |
| `delete_prefix` | Remove keys matching pattern |
| `acquire_lock` | Attempt to acquire distributed lock |
| `release_lock` | Release distributed lock |

### Status Labels

| `status` Value | Description |
|----------------|-------------|
| `hit` | Cache hit |
| `miss` | Cache miss |
| `ok` | Operation succeeded |
| `error` | Operation failed |
| `acquired` | Lock acquired |
| `busy` | Lock held by another process |
| `released` | Lock released |
| `mismatch` | Lock token mismatch (not owner) |
| `unavailable` | Redis unreachable |

---

## 8. Graceful Degradation Matrix

| Feature | Redis Available | Redis Unavailable |
|---------|----------------|-------------------|
| API Requests | Full functionality | Serves requests |
| Authentication | JWT validation (stateless) | JWT validation (stateless) |
| RBAC | Cached permission lookups | Database permission lookups |
| Rate Limiting | Enforced per-endpoint | All requests allowed |
| Idempotency | Request deduplication | No deduplication |
| Caching | Full cache layer | Cache misses (no errors) |
| Background Jobs | Queued via ARQ | Jobs dropped with warning |
| Distributed Locks | Lock acquisition | Locks not acquired (fail-closed) |

The application is designed to serve requests even when Redis is completely unavailable. Degradation is observable via metrics and logs.

Source: `src/pawguard/redis/client.py:30-78`
