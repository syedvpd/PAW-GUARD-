# Auth Module

JWT authentication, role-based access control (RBAC), session management, MFA, OAuth, and profile management for the entire PawGuard ecosystem.

---

## Architecture

```
auth/
  router.py          # 22 API endpoints
  admin_router.py    # Admin user/role management endpoints
  service.py         # AuthService + AdminService (business logic)
  repository.py      # Data access (User, Session, Role, Permission repos)
  models.py          # ORM models + AuthAuditEventType enum (159 event types)
  schemas.py         # Pydantic request/response DTOs
  dependencies.py    # FastAPI DI: get_current_user, CurrentUser dataclass
  rbac.py            # RequirePermission dependency, permission resolution
  exceptions.py      # Auth-specific error types
  permission_codes.py # Central registry of 154+ permission codes
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `User` | `users` | Core user record. `fcm_token`, `push_notifications_enabled`, `mfa_enabled` |
| `Role` | `roles` | Named role (17 seeded). `is_system` flag |
| `Permission` | `permissions` | Permission code (e.g. `rescue:create`) |
| `RolePermission` | `role_permissions` | M:N role-permission grant |
| `UserRole` | `user_roles` | M:N user-role assignment |
| `UserSession` | `user_sessions` | Active session with inactivity tracking |
| `RefreshToken` | `refresh_tokens` | Refresh token (rotation, reuse detection) |
| `MFADevice` | `mfa_devices` | TOTP device per user |
| `PasswordResetToken` | `password_reset_tokens` | One-hour opaque token |
| `EmailVerificationToken` | `email_verification_tokens` | Email verify token |
| `OAuthAccount` | `oauth_accounts` | Google/Apple linked accounts |
| `AuthAuditLog` | `auth_audit_logs` | Central audit trail for ALL modules |

## RBAC System

```
17 Roles (seeded):
  super_admin, rescue_centre_admin, rescue_coordinator, rescue_agent,
  veterinarian, shelter_manager, adoption_coordinator, foster_coordinator,
  volunteer_coordinator, inventory_manager, finance_user, volunteer,
  foster_family, donor, general_public, app_user

154+ Permission Codes:
  rescue:create/read/update/delete/verify/dispatch/execute
  medical:create/read/update/delete/clearance
  adoption:read/process/approve/lock
  shelter:read/update/manage_kennels/transfer
  foster:create/read/update/approve
  volunteer:create/read/update/schedule
  inventory:create/read/update/delete
  vehicle:read/assign/update
  finance:read/create/reconcile/update/delete/export
  donation:read/manage/update
  notification:manage
  system:admin/read/write
  dashboard:rescue/shelter/medical/adoption/foster/volunteer/inventory/finance/donor
  ... and more
```

**Permission Resolution (`rbac.py`):**
1. `RequirePermission("code")` FastAPI dependency
2. Admin bypass: `super_admin` / `system:admin` skip all checks
3. Redis-cached role-to-permission lookup (300s TTL)
4. Falls back to DB query on cache miss

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/auth/register` | Public (rate-limited) | Register new account |
| POST | `/auth/login` | Public (rate-limited) | Login, returns JWT pair |
| POST | `/auth/mfa/verify` | Public (rate-limited) | Complete MFA login |
| POST | `/auth/refresh` | Public (rate-limited) | Rotate refresh token |
| POST | `/auth/logout` | Authenticated | Revoke session |
| POST | `/auth/logout-all` | Authenticated | Revoke all sessions |
| GET | `/auth/me` | Authenticated | Get profile |
| PUT | `/auth/me` | Authenticated | Update profile + FCM token |
| GET | `/auth/sessions` | Authenticated | List active sessions |
| DELETE | `/auth/sessions/{id}` | Authenticated | Revoke specific session |
| POST | `/auth/password/change` | Authenticated (rate-limited) | Change password |
| POST | `/auth/password/reset/request` | Public (rate-limited) | Request reset email |
| POST | `/auth/password/reset/confirm` | Public (rate-limited) | Confirm reset with token |
| POST | `/auth/email/verify/request` | Authenticated (rate-limited) | Request verification |
| POST | `/auth/email/verify/confirm` | Public (rate-limited) | Confirm verification |
| POST | `/auth/mfa/enroll` | Authenticated | Start MFA enrollment |
| POST | `/auth/mfa/enroll/confirm` | Authenticated (rate-limited) | Confirm MFA enrollment |
| POST | `/auth/mfa/disable` | Authenticated (rate-limited) | Disable MFA |
| POST | `/auth/oauth/login` | Public (rate-limited) | OAuth login (Google/Apple) |
| GET | `/auth/oauth/accounts` | Authenticated | List linked accounts |
| POST | `/auth/oauth/link` | Authenticated | Link OAuth account |
| DELETE | `/auth/oauth/accounts/{id}` | Authenticated | Unlink OAuth account |

## Key Flows

### Login Flow
```
Client -> POST /auth/login {email, password}
  -> Verify credentials (argon2)
  -> Check account lockout (5 failed -> 15min lock)
  -> Create UserSession (inactivity timeout: 30 days)
  -> Create RefreshToken
  -> Generate JWT access token (roles in claims)
  -> Audit: LOGIN_SUCCESS
  -> Response: {access_token, refresh_token, user}
```

### MFA Flow
```
Login returns MFARequiredResponse -> Client POST /auth/mfa/verify {code}
  -> Verify TOTP code against stored secret
  -> Audit: MFA_VERIFIED + LOGIN_SUCCESS
  -> Full JWT pair returned
```

### Token Refresh Flow
```
Client -> POST /auth/refresh {refresh_token}
  -> Validate refresh token (not revoked, not expired)
  -> Rotation: revoke old token, create new pair
  -> Reuse detection: if old token reused, revoke ALL sessions
  -> Audit: REFRESH or REFRESH_REUSE_DETECTED
```

### Password Reset Flow
```
Request: POST /auth/password/reset/request {email}
  -> Generate opaque token, hash, store with 1-hour expiry
  -> Audit: PASSWORD_RESET_REQUESTED
  -> Return raw token (to be emailed)

Confirm: POST /auth/password/reset/confirm {token, new_password}
  -> Hash token, lookup, validate expiry
  -> Hash new password, update user
  -> Revoke ALL sessions (security)
  -> Audit: PASSWORD_RESET_COMPLETED
```

### Account Lockout
```
Failed login counter (in-memory, per-request):
  -> 5 failures within window
  -> AccountLockedError raised
  -> Lockout duration: 15 minutes
  -> Audit: ACCOUNT_LOCKED
```

## Cross-Module Dependencies

| Dependency | Direction | Purpose |
|------------|-----------|---------|
| `AuthAuditLog` | Outbound | Every module writes audit events here |
| `User.fcm_token` | Outbound | Push notification token storage |
| `User.push_notifications_enabled` | Outbound | Global push toggle |
| `UserRole` | Outbound | Foster/volunteer role granting |
| `CacheService` (Redis) | Outbound | Permission caching, session cache |
| `arq pool` | Outbound | Email delivery background jobs |
