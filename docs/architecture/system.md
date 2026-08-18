# System Architecture

Scope: Full-stack system topology, deployment model, request lifecycle, and infrastructure design.

---

## 1. Deployment Topology

PawGuard runs as two Docker containers orchestrated via `docker-compose.yml`:

```
+------------------+          +------------------+
|    api (FastAPI) |          |  worker (ARQ)    |
|  uvicorn :8000   |          |  arq worker      |
+--------+---------+          +--------+---------+
         |                            |
         |        +----------+        |
         +------->|  Redis   |<-------+
                  | (queue + |
                  |  cache)  |
                  +-----+----+
                        |
         +--------------+--------------+
         |                             |
+--------v---------+       +-----------v--------+
|   PostgreSQL     |       |  S3 / Supabase     |
|  (primary)       |       |  Object Storage    |
|  + replica       |       +--------------------+
+------------------+
```

### Container Roles

| Container | Entrypoint | Purpose |
|-----------|-----------|---------|
| `api` | `uvicorn pawguard.main:app --host 0.0.0.0 --port 8000` | Serves HTTP API, handles all client requests |
| `worker` | `arq pawguard.workers.arq_worker.WorkerSettings` | Processes background jobs, scheduled cron tasks, outbox polling |

Both containers share the same codebase image and environment variables. The API container mounts source code for hot-reload in development.

### Health Endpoints

| Endpoint | Purpose | Checks |
|----------|---------|--------|
| `GET /health` | Liveness probe | Always returns `200 OK` |
| `GET /live` | Liveness probe | Always returns `200 OK` |
| `GET /ready` | Readiness probe | Verifies PostgreSQL + Redis connectivity |
| `GET /metrics` | Prometheus exposition | Returns RED metrics, DB pool stats, Redis telemetry |

Source: `src/pawguard/main.py:166-216`

---

## 2. Request Lifecycle

Every HTTP request traverses a fixed pipeline enforced by middleware and FastAPI dependencies:

```
Client Request
    |
    v
[1] RequestIDMiddleware          -- assigns x-request-id, x-trace-id, x-span-id
    |
    v
[2] RequestLoggingMiddleware     -- RED metrics, structured request log
    |
    v
[3] RequestBodySizeMiddleware    -- rejects bodies > 10 MB (configurable)
    |
    v
[4] IdempotencyMiddleware       -- deduplicates mutating requests via Redis
    |
    v
[5] SecurityHeadersMiddleware   -- CSP, HSTS, X-Frame-Options, cache control
    |
    v
[6] TrustedHostMiddleware       -- validates Host header
    |
    v
[7] CORSMiddleware              -- cross-origin resource sharing
    |
    v
[8] FastAPI Router              -- route matching, dependency injection
    |
    v
[9] Auth Dependencies           -- JWT decode, session validation, RBAC check
    |
    v
[10] Request Validation         -- Pydantic model validation (automatic)
    |
    v
[11] Service Layer              -- business logic execution
    |
    v
[12] Repository Layer           -- database queries via SQLAlchemy async
    |
    v
[13] Response Validation        -- Pydantic response model serialization
    |
    v
[14] ApiResponse Envelope       -- { success, data, message } wrapper
    |
    v
Client Response
```

Source: `src/pawguard/main.py:150-166`

---

## 3. Middleware Stack

Middleware executes in reverse order of registration (last added = first executed):

| Order | Middleware | Source | Purpose |
|-------|-----------|--------|---------|
| 1 (outermost) | `CORSMiddleware` | FastAPI built-in | Cross-origin requests |
| 2 | `TrustedHostMiddleware` | FastAPI built-in | Host header validation |
| 3 | `SecurityHeadersMiddleware` | `core/middleware.py:156` | CSP, HSTS, X-Frame-Options |
| 4 | `RequestBodySizeMiddleware` | `core/middleware.py:177` | Body size limit (10 MB default) |
| 5 | `IdempotencyMiddleware` | `core/idempotency.py:40` | Request deduplication via Redis |
| 6 | `RequestLoggingMiddleware` | `core/middleware.py:70` | RED metrics + structured logging |
| 7 (innermost) | `RequestIDMiddleware` | `core/middleware.py:31` | Request/trace/span ID propagation |

---

## 4. Environment Configuration

All configuration is centralized in `core/config.py` via Pydantic Settings, loaded from environment variables (`.env` file in development).

### Environment Tiers

| Tier | `environment` | Docs Enabled | Debug Mode |
|------|--------------|-------------|------------|
| Local | `local` | Yes | Optional |
| Staging | `staging` | Yes | No |
| Production | `production` | No | No |
| Test | `test` | No | No |

### Configuration Groups

| Group | Prefix/Keys | Purpose |
|-------|------------|---------|
| App | `APP_NAME`, `ENVIRONMENT`, `DEBUG`, `API_V1_PREFIX` | Application identity |
| Database | `DATABASE_URL`, `DATABASE_REPLICA_URL`, pool settings | PostgreSQL connections |
| Redis | `REDIS_URL` | Cache, queue, rate limiting |
| JWT | `JWT_PRIVATE_KEY_PEM`, `JWT_PUBLIC_KEY_PEM`, algorithm | Token signing (RS256) |
| MFA | `MFA_ENCRYPTION_KEY`, `MFA_MANDATORY_FOR_ADMINS` | TOTP secret encryption |
| OAuth | `GOOGLE_OAUTH_CLIENT_ID`, `APPLE_OAUTH_CLIENT_ID` | Social login |
| S3 | `S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, endpoint | Object storage |
| Mail | `MAIL_FROM`, `MAIL_HOST`, `BREVO_API_KEY` | Email delivery |
| FCM | `FCM_CREDENTIALS_PATH`, `FCM_CREDENTIALS_JSON` | Push notifications |
| Payments | `PAYMENT_PROVIDER`, `RAZORPAY_KEY_ID` | Payment processing |
| Rate Limiting | `RATE_LIMITING_ENABLED`, per-endpoint limits | Throttling |
| CORS | `CORS_ORIGINS`, `WEB_APP_URL`, `ADMIN_APP_URL` | Cross-origin policy |

Source: `src/pawguard/core/config.py:31-236`

---

## 5. Error Handling

The application uses a centralized exception hierarchy defined in `core/exceptions.py`. Every exception maps to a standard HTTP status code and machine-readable error code.

### Exception Hierarchy

```
AppException (base)
    NotFoundError           -- 404 NOT_FOUND
    ValidationFailedError   -- 422 VALIDATION_FAILED
    ConflictError           -- 409 CONFLICT
    UnauthorizedError       -- 401 UNAUTHORIZED
    ForbiddenError          -- 403 FORBIDDEN
    TooManyRequestsError    -- 429 TOO_MANY_REQUESTS
    StorageError            -- 503 STORAGE_UNAVAILABLE
```

### Response Envelope

Every error response follows the standard envelope:

```json
{
    "success": false,
    "error": {
        "code": "NOT_FOUND",
        "message": "Dog profile not found.",
        "details": null
    }
}
```

### Exception Handler Registration

| Handler | HTTP Status | Source |
|---------|------------|--------|
| `AppException` | Per exception class | `core/exceptions.py:144` |
| `RequestValidationError` | 422 | `core/exceptions.py:157` |
| `ResponseValidationError` | 500 | `core/exceptions.py:184` |
| `ValueError` | 422 | `core/exceptions.py:202` |
| `StarletteHTTPException` | Per exception | `core/exceptions.py:218` |
| `SQLAlchemyError` | 409/422/500 | `core/exceptions.py:225` |
| Unhandled `Exception` | 500 | `core/exceptions.py:297` |

SQLAlchemy errors are mapped to semantic HTTP codes: unique violations become 409, foreign key violations become 409, data errors become 422.

---

## 6. Observability

### Structured Logging

Logging uses `structlog` with environment-aware output:

| Environment | Renderer | Format |
|-------------|----------|--------|
| Local | `ConsoleRenderer` | Human-readable colored output |
| Staging/Production | `JSONRenderer` | Machine-parseable JSON |

Every log entry includes:
- `request_id` - Unique per-request identifier
- `trace_id` - Distributed trace identifier
- `span_id` - Current span identifier
- `user_id` - Authenticated user (when applicable)
- ISO-8601 timestamp

Sensitive fields (`password`, `token`, `secret`, `authorization`) are automatically redacted.

Source: `src/pawguard/core/logging.py:16-81`

### Metrics

The application exposes a Prometheus-compatible `/metrics` endpoint with:

| Metric Type | Examples | Purpose |
|-------------|---------|---------|
| Counters | `http_requests_total`, `db_queries_total`, `worker_jobs_total` | Request/error counting |
| Gauges | `http_requests_in_flight`, `db_pool_size` | Current state |
| Histograms | `http_request_duration_ms`, `db_query_duration_ms`, `worker_job_duration_ms` | Latency distribution |

Metrics are collected in-memory using fixed-memory O(1) histogram accumulators to prevent memory leaks under high throughput.

Source: `src/pawguard/core/metrics.py:1-232`

### Distributed Tracing

Every request receives three identifiers propagated through middleware:

| Header | Purpose | Source |
|--------|---------|--------|
| `X-Request-ID` | Unique request identifier | `RequestIDMiddleware` or client-provided |
| `X-Trace-ID` | Distributed trace correlation | `traceparent` header or generated |
| `X-Span-ID` | Current operation span | Generated per request |

These headers are included in both request context and response headers.

---

## 7. Security Architecture

### Transport Security

- HTTPS enforced via HSTS header: `max-age=63072000; includeSubDomains`
- CORS restricted to configured origins (localhost in dev, Vercel domains in production)
- Trusted host middleware validates `Host` header

### Content Security Policy

| Context | CSP Policy |
|---------|-----------|
| API endpoints | `default-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'` |
| Docs (`/docs`, `/redoc`) | Extended with `cdn.jsdelivr.net` for Swagger UI assets |

### Security Headers

Applied to every response via `SecurityHeadersMiddleware`:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` |
| `Cache-Control` | `no-store, no-cache, must-revalidate` (API routes) |

Source: `src/pawguard/core/middleware.py:131-174`

---

## 8. Client Support

The backend serves four client types through a single unified API:

| Client | Type | Token Transport | Device Header |
|--------|------|----------------|---------------|
| Public Website | Web | Cookie (`pg_access_token`) | `X-Client-Type: web` |
| Admin Portal | Web | Cookie (`pg_access_token`) | `X-Client-Type: web` |
| Rescue Staff App | Mobile | Bearer token | `X-Client-Type: mobile` |
| Executive App | Mobile | Bearer token | `X-Client-Type: mobile` |

All clients share the same API version prefix (`/api/v1`) and authentication mechanism. Client-specific behavior is handled via the `X-Client-Type` and `X-Device-ID` headers.

Source: `src/pawguard/core/constants.py:13-32`

---

## 9. API Versioning

All endpoints are versioned under `/api/v1`. The version prefix is configurable via `API_V1_PREFIX` (default: `/api/v1`).

Breaking changes require a new version prefix (`/api/v2`). Non-breaking additions (new fields, new endpoints) are made within the current version.

Source: `src/pawguard/core/config.py:73`
