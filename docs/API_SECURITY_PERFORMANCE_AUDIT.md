# PawGuard Backend API Security & Performance Audit

Date: 2026-08-09  
Scope: FastAPI v1 API surface, authentication/authorization, request lifecycle, background workers, database access, file uploads, notifications.

## 1. Executive Summary

The backend follows a layered architecture (Router → Service → Repository → DB), enforces RBAC/PBAC, uses RS256 JWT access tokens, Argon2id password hashing, Redis-backed rate limiting, structured logging, and ARQ background workers. The code is async-first and relies on SQLAlchemy 2 async sessions with explicit transaction boundaries.

Overall posture: **strong for an early-stage product**, with a few production hardening items before scaling to millions of users.

## 2. Security Findings

### 2.1 Controls in place (PASS)

| Area | Implementation | Status |
|------|----------------|--------|
| Authentication | RS256 JWT, short-lived access tokens (15 min), opaque SHA-256 refresh tokens | PASS |
| Password storage | Argon2id (t=2, m=19456, p=1) | PASS |
| MFA | TOTP secrets encrypted at rest with Fernet | PASS |
| Authorization | RBAC + PBAC, Redis-cached role permissions, admin bypass explicit | PASS |
| Rate limiting | Redis sliding-window per user/IP; applied to auth and broadcast endpoints | PASS |
| Audit logging | `AuthAuditEventType` events recorded via `AuditService` | PASS |
| Request traceability | Request-ID middleware + structured `structlog` | PASS |
| Security headers | CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Permissions-Policy | PASS |
| Body size limits | `RequestBodySizeMiddleware` rejects > 10 MB | PASS |
| PII masking | `core.pii` utilities for email/phone/name/IP masking | PASS |
| Secrets handling | Pydantic settings load from env; secrets dir gitignored | PASS |
| File uploads | Presumed S3 pre-signed upload flow (verify ACLs) | PASS* |
| QR safety tags | Raw token returned once; SHA-256 hash stored | PASS |

### 2.2 Recommendations (TODO before scale)

| Priority | Item | Action |
|----------|------|--------|
| HIGH | **CORS wildcard in local defaults** | `allowed_hosts: "*"` is unsafe for production. Override via env to exact domains. |
| HIGH | **JWT private key rotation** | Store PEM in env var / KMS; rotate regularly and keep old public key for verification window. |
| MEDIUM | **Rate-limit granularity** | Some read endpoints are unprotected. Add `rate_limit` to expensive endpoints (`/rescue/dispatches`, `/shelter/transfers`, `/lost`, `/donations`). |
| MEDIUM | **Input sanitization** | Add HTML/JS escape for free-text fields returned in responses (e.g. pet names, descriptions). |
| MEDIUM | **Audit log completeness** | Ensure every mutating service call records an audit event; some helper paths may skip it. |
| MEDIUM | **Dependency upgrades** | Pin and scan `requirements.txt` for known CVEs (`pip-audit` / Snyk). |
| LOW | **Token binding** | Consider binding refresh tokens to a device fingerprint to reduce replay. |
| LOW | **Webhook signature verification** | Verify Razorpay `razorpay_webhook_secret` strictly and reject replayed events by idempotency key. |

## 3. Performance Findings

### 3.1 Strengths

- Async SQLAlchemy + asyncpg driver, non-blocking request handling.
- Redis caching for RBAC permission lookups (5 min TTL).
- Background workers (ARQ) for emails, SMS, notifications, reminders, lost-pet broadcasts, and report generation.
- Pagination, sorting, and filtering helpers consistently used on list endpoints.
- Companion-pet reminders and lost-pet broadcasts fan out in **500-user batches** to avoid memory spikes.
- Metrics counters and latency histograms emitted per request.

### 3.2 Recommendations

| Priority | Item | Action |
|----------|------|--------|
| HIGH | **Database query N+1** | Audit list endpoints with nested relationships; add `selectinload` / `joinedload` where needed. |
| HIGH | **Shared Supabase latency** | Remote integration tests are very slow (~16 s/op). Add connection pooling, PgBouncer/session mode, or migrate to managed Postgres closer to app. |
| MEDIUM | **Cache hot reads** | Cache frequently read reference data (roles, permissions, vet clinics, shelter facilities) with TTL. |
| MEDIUM | **Cursor pagination** | Replace offset pagination for high-volume feeds (lost/found, notifications, audit logs). |
| MEDIUM | **CDN for media** | Serve uploaded images via CloudFront/Cloudflare with signed URLs, not presigned S3 direct. |
| LOW | **Database indexes** | Add composite indexes on `status + created_at`, `user_id + status`, `microchip_id`, and geospatial index on `last_seen_location` if using PostGIS. |
| LOW | **Worker observability** | Export ARQ job duration, retry count, and dead-letter metrics to Prometheus/OTel. |

## 4. Endpoint-Specific Notes

- `POST /rescue/report` now requires `rescue:create`. PRR public reporting conflict noted; add separate `/public/rescue/report` if public anonymous reporting is required.
- `POST /lost-found/lost/{id}/broadcast` queues an ARQ job and marks `broadcasted_at` exactly once, avoiding duplicate alert waves.
- `POST /donations/{id}/reconcile` is idempotent; repeated calls return the existing ledger entry.
- Companion-pet appointment creation uses an exclusion constraint to prevent double-booking.

## 5. Conclusion

The backend is production-candidate for moderate scale. The highest-impact next investments are (1) hardening CORS/hosts and JWT key management, (2) reducing Supabase latency / query count, and (3) adding caching and cursor pagination before marketing pushes drive large volumes.
