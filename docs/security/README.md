# Security Overview

PawGuard implements a defense-in-depth security architecture across authentication, authorization, data protection, and infrastructure layers.

## Security Architecture

### Authentication Layer
- JWT RS256 asymmetric token signing (`src/pawguard/core/security.py`)
- Argon2id password hashing with OWASP-recommended parameters (19 MiB, t=2, p=1)
- TOTP-based MFA with Fernet-encrypted secrets at rest
- OAuth 2.0 social login (Google, Apple) with audience validation
- Refresh token rotation with reuse detection

### Authorization Layer
- Role-Based Access Control (RBAC) with permission codes (`src/pawguard/modules/auth/rbac.py`)
- Redis-cached role-to-permission lookups (300s TTL)
- Admin bypass restricted to `super_admin` and `system:admin` roles only
- 154 granular permission codes across 20+ domains (`src/pawguard/modules/auth/permission_codes.py`)

### Rate Limiting
- Redis-backed sliding window rate limiter (`src/pawguard/core/rate_limiter.py`)
- Per-endpoint configuration with user/IP keying
- Separate limits for login, registration, MFA, password reset, and OAuth endpoints

### Data Protection
- Fernet encryption for MFA TOTP secrets at rest
- Structured audit logging with before/after state snapshots
- Soft-delete pattern for operational records (no hard deletes)
- PII handling utilities (`src/pawguard/core/pii.py`)

### Infrastructure Security
- CORS whitelist configuration
- Trusted host middleware
- Security headers middleware
- Request body size limits (10 MB default)
- Idempotency middleware for write operations

## Key Security Files

| File | Purpose |
|------|---------|
| `src/pawguard/core/security.py` | Password hashing, JWT primitives, MFA encryption |
| `src/pawguard/modules/auth/rbac.py` | RBAC permission resolution |
| `src/pawguard/modules/auth/dependencies.py` | Current user extraction, session validation |
| `src/pawguard/modules/auth/service.py` | Authentication business logic |
| `src/pawguard/core/rate_limiter.py` | Rate limiting implementation |
| `src/pawguard/core/middleware.py` | Security headers, request validation |

## Security Headers

Applied via `SecurityHeadersMiddleware`:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Cache-Control: no-store, no-cache, must-revalidate`
- `Referrer-Policy: strict-origin-when-cross-origin`

## Audit Trail

All security-relevant events are logged to `auth_audit_logs` with:
- Actor user ID
- IP address and user agent
- Event type (from `AuthAuditEventType` enum)
- Optional metadata, before_state, after_state

## Environment Configuration

Security-sensitive settings are loaded from environment variables (never hardcoded):
- `JWT_PRIVATE_KEY_PEM` / `JWT_PUBLIC_KEY_PEM` - RS256 keypair
- `MFA_ENCRYPTION_KEY` - Fernet key for MFA secrets
- `GOOGLE_OAUTH_CLIENT_ID` / `APPLE_OAUTH_CLIENT_ID` - OAuth audience validation
- `DATABASE_URL` - Database connection string
- `REDIS_URL` - Redis connection for sessions and caching
