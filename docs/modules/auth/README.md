# Auth Module

> **Source:** `src/pawguard/modules/auth/`
> **Routers:** `router.py` (22 endpoints) · `admin_router.py` (admin CRUD)
> **Service:** `service.py` — `AuthService`, `AdminService`
> **RBAC:** `rbac.py` · `permission_codes.py` (154 codes)

## Purpose

The Auth module is the security backbone of the PawGuard backend. It owns identity management, JWT-based authentication, refresh-token rotation with reuse detection, session lifecycle, TOTP multi-factor authentication, OAuth social login (Google, Apple), role-based access control (RBAC), and centralised audit logging.

Every other module delegates authentication and authorisation to this module through the `RequirePermission` FastAPI dependency and the `CurrentUser` injection pattern.

## Architecture

```
auth/
├── router.py              # 22 authenticated endpoints (/auth/*)
├── admin_router.py        # Admin user/role CRUD (/admin/*)
├── service.py             # AuthService + AdminService business logic
├── repository.py          # Data-access (User, Session, RefreshToken, MFA, OAuth, …)
├── models.py              # ORM: User, Role, Permission, UserSession, RefreshToken,
│                          #   MFADevice, OAuthAccount, PasswordResetToken,
│                          #   EmailVerificationToken, AuthAuditLog, …
├── schemas.py             # Pydantic request/response DTOs
├── admin_schemas.py       # Admin-specific DTOs
├── rbac.py                # RequirePermission dependency, Redis-cached permission lookup
├── permission_codes.py    # Central registry of 154 permission codes
├── dependencies.py        # get_current_user, get_current_session, CurrentUser
├── exceptions.py          # Domain-specific exceptions
└── audit.py               # get_audit_service helper
```

### Models

| Model | Table | Purpose |
|---|---|---|
| `User` | `users` | Identity record with email, password hash, profile fields, MFA flag, lockout counters, FCM token |
| `Role` | `roles` | Named role (e.g. `super_admin`, `rescue_agent`) with `is_system` flag |
| `Permission` | `permissions` | Granular permission code (e.g. `rescue:create`) |
| `RolePermission` | `role_permissions` | Many-to-many join |
| `UserRole` | `user_roles` | Many-to-many join |
| `UserSession` | `user_sessions` | Active session with device info, IP, expiry, revocation |
| `RefreshToken` | `refresh_tokens` | Opaque refresh token (hashed), rotation chain via `rotated_to_id` |
| `MFADevice` | `mfa_devices` | TOTP secret (encrypted), verified flag |
| `PasswordResetToken` | `password_reset_tokens` | Time-limited reset token (hashed) |
| `EmailVerificationToken` | `email_verification_tokens` | Time-limited verify token (hashed) |
| `OAuthAccount` | `oauth_accounts` | Linked social accounts (provider, provider_user_id) |
| `AuthAuditLog` | `auth_audit_logs` | Immutable audit trail (159 event types) |

## State Machines

### Account Lockout

```
                   Failed login
                       │
                       ▼
              ┌─────────────────┐
              │  failed_count++  │
              └────────┬────────┘
                       │
            failed_count >= 5?
            ┌─── No ──┤─── Yes ───┐
            │          │           │
            ▼          │           ▼
       (no lock)       │   ┌──────────────┐
                       │   │ locked_until  │
                       │   │ = now + 15min │
                       │   └──────┬───────┘
                       │          │
                       │   Login attempted?
                       │   ┌── No ──┤── Yes ───┐
                       │   │        │           │
                       │   │        │    locked_until > now?
                       │   │        │   ┌─ No ──┤── Yes ──┐
                       │   │        │   │        │         │
                       │   │        │   ▼        │         ▼
                       │   │        │ reset()    │   AccountLockedError
                       │   │        │            │
```

### MFA Enrollment

```
POST /mfa/enroll          →  generates TOTP secret, returns provisioning URI
        │
        ▼
POST /mfa/enroll/confirm  →  verifies 6-digit code
        │
        ├── Invalid code  →  InvalidMFACodeError (retry)
        │
        └── Valid code    →  device.is_verified = True
                            user.mfa_enabled = True
                            audit: MFA_ENROLLED
                            push: "MFA Enabled"
```

### Password Reset

```
POST /password/reset/request   →  generates opaque token, hashes, stores
        │
        ▼
   Email sent with reset URL
        │
        ▼
POST /password/reset/confirm   →  validates token hash, not expired, not used
        │
        ├── Invalid/expired  →  InvalidTokenError
        │
        └── Valid            →  hash new password
                                mark token used
                                revoke all sessions
                                audit: PASSWORD_RESET_COMPLETED
```

## Endpoint Catalog

### Auth Router (`/auth`)

| # | Method | Path | Permission | Description |
|---|--------|------|------------|-------------|
| 1 | `POST` | `/auth/register` | Public | Register new account; enqueues verification email |
| 2 | `POST` | `/auth/login` | Public | Login; returns tokens or MFA pre-auth token |
| 3 | `POST` | `/auth/mfa/verify` | Public (pre-auth) | Complete MFA login with TOTP code |
| 4 | `POST` | `/auth/refresh` | Public (refresh token) | Rotate refresh token, issue new access token |
| 5 | `POST` | `/auth/logout` | Authenticated | Revoke current session + refresh tokens |
| 6 | `POST` | `/auth/logout-all` | Authenticated | Revoke all sessions except current |
| 7 | `GET` | `/auth/me` | Authenticated | Get current user profile |
| 8 | `PUT` | `/auth/me` | Authenticated | Update profile (name, phone, avatar, FCM, …) |
| 9 | `GET` | `/auth/sessions` | Authenticated | List active sessions |
| 10 | `DELETE` | `/auth/sessions/{id}` | Authenticated | Revoke a specific session |
| 11 | `POST` | `/auth/password/change` | Authenticated | Change password (logs out other sessions) |
| 12 | `POST` | `/auth/password/reset/request` | Public | Request password reset email |
| 13 | `POST` | `/auth/password/reset/confirm` | Public | Confirm reset with token + new password |
| 14 | `POST` | `/auth/email/verify/request` | Authenticated | Resend verification email |
| 15 | `POST` | `/auth/email/verify/confirm` | Public | Confirm email with token |
| 16 | `POST` | `/auth/mfa/enroll` | Authenticated | Start MFA enrollment (returns secret + URI) |
| 17 | `POST` | `/auth/mfa/enroll/confirm` | Authenticated | Confirm MFA enrollment with TOTP code |
| 18 | `POST` | `/auth/mfa/disable` | Authenticated | Disable MFA (password or TOTP required; admins blocked) |
| 19 | `POST` | `/auth/oauth/login` | Public | OAuth login (Google id_token / Apple JWT) |
| 20 | `GET` | `/auth/oauth/accounts` | Authenticated | List linked OAuth accounts |
| 21 | `POST` | `/auth/oauth/link` | Authenticated | Link additional OAuth account |
| 22 | `DELETE` | `/auth/oauth/accounts/{id}` | Authenticated | Unlink OAuth account |

### Admin Router (`/admin`)

| # | Method | Path | Permission | Description |
|---|--------|------|------------|-------------|
| 1 | `GET` | `/admin/roles` | `system:admin` | List all roles |
| 2 | `POST` | `/admin/roles` | `system:admin` | Create role with permissions |
| 3 | `GET` | `/admin/roles/{id}` | `system:admin` | Get role detail |
| 4 | `PUT` | `/admin/roles/{id}` | `system:admin` | Update role description/permissions |
| 5 | `DELETE` | `/admin/roles/{id}` | `system:admin` | Delete non-system role |
| 6 | `GET` | `/admin/permissions` | `system:admin` | List all permission codes |
| 7 | `GET` | `/admin/users` | `system:admin` | List all users |
| 8 | `POST` | `/admin/users` | `system:admin` | Create user with roles |
| 9 | `GET` | `/admin/users/{id}` | `system:admin` | Get user detail |
| 10 | `PUT` | `/admin/users/{id}` | `system:admin` | Update user (name, roles, active, password) |
| 11 | `DELETE` | `/admin/users/{id}` | `system:admin` | Soft-delete user |
| 12 | `POST` | `/admin/users/restore-and-reset` | `system:admin` | Restore soft-deleted user + reset password |

## RBAC System

### Permission Codes

154 codes across 18 domains, defined in `permission_codes.py`:

| Domain | Codes |
|--------|-------|
| System | `system:read`, `system:write`, `system:admin` |
| User | `user:read`, `user:create`, `user:update`, `user:delete`, `user:assign_role` |
| Rescue | `rescue:create`, `rescue:read`, `rescue:update`, `rescue:delete`, `rescue:verify`, `rescue:dispatch`, `rescue:execute`, `rescue:write` |
| Vehicle | `vehicle:read`, `vehicle:assign`, `vehicle:update` |
| Shelter | `shelter:read`, `shelter:update`, `shelter:manage_kennels`, `shelter:transfer` |
| Medical | `medical:create`, `medical:read`, `medical:update`, `medical:clearance`, `medical:delete` |
| Adoption | `adoption:read`, `adoption:process`, `adoption:approve`, `adoption:lock`, `adoption:delete` |
| Foster | `foster:create`, `foster:read`, `foster:update`, `foster:approve`, `foster:delete` |
| Volunteer | `volunteer:create`, `volunteer:read`, `volunteer:update`, `volunteer:schedule`, `volunteer:delete` |
| Inventory | `inventory:create`, `inventory:read`, `inventory:update`, `inventory:delete` |
| Finance | `finance:read`, `finance:create`, `finance:reconcile`, `finance:update`, `finance:delete`, `finance:export` |
| Reports | `reports:read`, `reports:create`, `reports:export_pdf`, `reports:export_csv`, `reports:export_excel` |
| Dashboards | `dashboard:rescue`, `dashboard:shelter`, `dashboard:medical`, `dashboard:adoption`, `dashboard:foster`, `dashboard:volunteer`, `dashboard:inventory`, `dashboard:finance`, `dashboard:donor` |
| Donation | `donation:read`, `donation:manage`, `donation:update`, `donations:write` |
| Public | `public:read`, `public:create` |
| Audit | `audit:read` |
| Grievance | `grievance:create`, `grievance:read`, `grievance:update`, `grievance:assign`, `grievance:comment`, `complaints:write` |
| Notifications | `notification:read`, `notification:manage`, `notifications:write` |
| Companion Pet | `companion_pet:create`, `companion_pet:read`, `companion_pet:update`, `companion_pet:delete`, `companion_pet:medical_upload`, `safety_tag:manage`, `vet_clinic:read`, `vet_clinic:manage`, `appointment:create`, `appointment:read`, `appointment:cancel`, `appointment:manage` |
| Lost & Found | `lost_found:broadcast` |

### Roles (17 seeded)

| Role | Description |
|------|-------------|
| `super_admin` | System governance, RBAC, global config, audit review (bypass all checks) |
| `rescue_centre_admin` | Operational strategy, facility oversight, compliance |
| `rescue_admin` | Rescue workflow management |
| `rescue_coordinator` | Case assignment, dispatch, verification |
| `rescue_agent` | Field operations, status updates |
| `shelter_admin` | Shelter facility management |
| `shelter_staff` | Daily shelter operations |
| `veterinarian` | Medical records, clearance |
| `foster_coordinator` | Foster placement management |
| `foster_parent` | Foster application, care logs |
| `adoption_coordinator` | Adoption processing |
| `volunteer_coordinator` | Volunteer scheduling |
| `finance_admin` | Financial operations |
| `donor` | Donation management (own data) |
| `inventory_manager` | Stock management |
| `public_user` | Public portal access (default role on registration) |
| `system:admin` | Alias for bypass in `ADMIN_ROLES` set |

### RequirePermission Dependency

```python
# Usage in any router:
from pawguard.modules.auth.rbac import require_permission

@router.get("/resource", dependencies=[Depends(require_permission("rescue:read"))])
async def get_resource(...):
    ...
```

**Resolution flow:**
1. Extract JWT claims via `get_current_user`
2. If user holds `super_admin` or `system:admin` → **bypass** (returns immediately)
3. Check Redis cache (`rbac:roles:<sorted_names>`, TTL 300s)
4. Cache miss → query `permissions` JOIN `role_permissions` JOIN `roles`
5. If `permission_code` not in resolved set → raise `InsufficientPermissionsError`

## Session Management

| Property | Value |
|----------|-------|
| Access token lifetime | Configurable via `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Refresh token lifetime | Configurable via `REFRESH_TOKEN_EXPIRE_DAYS` (default 30) |
| Session inactivity timeout | `REFRESH_TOKEN_EXPIRE_DAYS` (30-day default) |
| Token storage | Refresh tokens stored as SHA-256 hashes |
| Rotation | Every `/refresh` call issues a new refresh token; old one is revoked with `rotated_to_id` chain |
| Reuse detection | If a revoked/rotated refresh token is reused → entire session is revoked (`refresh_token_reuse_detected`) |
| Cookie mode | Web clients (`X-Client-Type: web`) receive tokens as httponly, secure, SameSite=strict cookies |
| Body mode | Mobile clients receive tokens in the JSON response body |

## MFA (TOTP)

- **Enrollment:** `POST /mfa/enroll` generates a TOTP secret + provisioning URI; `POST /mfa/enroll/confirm` verifies a 6-digit code
- **Secret storage:** AES-encrypted at rest via `encrypt_mfa_secret()`; transparent re-encryption on legacy plaintext
- **Login gate:** If `user.mfa_enabled` or mandatory admin MFA → login returns a short-lived pre-auth token; `POST /mfa/verify` completes login
- **Admin enforcement:** Admins (holders of `system:admin`) cannot disable MFA; they must enroll before first login
- **Disable:** Requires either current password or valid TOTP code; admins are rejected with `MFADisableNotAllowedError`

## OAuth (Social Login)

| Provider | Verification method | Notes |
|----------|-------------------|-------|
| Google | `id_token` → `oauth2.googleapis.com/tokeninfo` | Validates `aud` matches configured client ID |
| Apple | JWT → `appleid.apple.com/auth/keys` (RS256) | Validates `aud` matches configured client ID |

**Flow:**
1. Client sends `provider_token` (id_token for Google, JWT for Apple)
2. Backend verifies token with provider's public endpoint
3. If `OAuthAccount` exists for `provider + provider_user_id` → login existing user
4. If user with same email exists → link account to existing user
5. Otherwise → auto-create new user with default role + link OAuth account

## Security

| Mechanism | Details |
|-----------|---------|
| Password hashing | Argon2id (via `argon2-cffi`); automatic rehash when cost params change |
| Password policy | Min 10 chars, uppercase, lowercase, digit |
| Account lockout | 5 failed attempts → 15-minute lock |
| Rate limiting | Per-endpoint (register: 5/hr, login: 10/min, MFA: 10/5min, password reset: 5/hr) |
| Token hashing | Refresh tokens stored as SHA-256 hashes (never plaintext) |
| MFA secret encryption | AES encryption at rest |
| OAuth audience validation | Google/Audience and Apple audience checked against server config |
| PII never logged | Structured logging only; no passwords, tokens, or secrets |

## Audit Log

The `AuthAuditLog` model records 159 event types across all modules. Auth-specific events include:

`login_success`, `login_failed`, `logout`, `logout_all`, `refresh`, `refresh_reuse_detected`, `password_change`, `password_reset_requested`, `password_reset_completed`, `email_verification_requested`, `email_verified`, `mfa_enrolled`, `mfa_verified`, `mfa_failed`, `mfa_disabled`, `session_revoked`, `registered`, `account_locked`, `profile_updated`, `oauth_login`, `oauth_linked`, `oauth_unlinked`, `admin_user_created`, `admin_user_updated`, `admin_user_deleted`, `admin_role_created`, `admin_role_updated`, `admin_role_deleted`

Each log entry captures: `user_id`, `event_type`, `ip_address`, `user_agent`, `event_metadata` (JSONB), `before_state`, `after_state`.

## Cross-Module Interactions

| Consumer Module | Integration |
|-----------------|-------------|
| All modules | `RequirePermission` dependency for endpoint protection |
| Rescue | Push notifications to coordinators/agents on incident dispatch |
| Notifications | FCM token storage on `User.fcm_token`; push preference on `User.push_notifications_enabled` |
| Outbox | Email jobs (verification, password reset) enqueued via `OutboxService` |
| Dog | `DogProfile.rescue_case_id` → `RescueRequest.id` (cross-module FK) |
| Medical | Mandatory MFA for veterinarians; medical clearance gates `is_adoptable` |
| Adoption | Default role assignment on registration (`public_user`) |

## Key Flows

### Registration → Email Verification → Login

```
1. POST /auth/register
   → hash password (argon2)
   → create User with default role
   → generate email verification token
   → enqueue send_email_verification_email_job via Outbox
   → audit: REGISTERED

2. User clicks email link → GET /verify-email?token=...

3. POST /auth/email/verify/confirm { token }
   → validate token (not expired, not used)
   → set user.is_verified = True, user.email_verified_at = now
   → audit: EMAIL_VERIFIED

4. POST /auth/login { email, password }
   → verify password
   → reset failed_login_count
   → create UserSession
   → create RefreshToken
   → create_access_token (JWT with user_id, session_id, roles)
   → audit: LOGIN_SUCCESS
   → return { access_token, refresh_token, user }
```

### MFA Login

```
1. POST /auth/login { email, password }
   → password valid + user.mfa_enabled = True
   → return { mfa_required: true, pre_auth_token }

2. POST /auth/mfa/verify { pre_auth_token, code }
   → decode pre_auth_token (type=PRE_AUTH, short-lived)
   → verify TOTP code against stored secret
   → issue access_token + refresh_token
   → audit: MFA_VERIFIED, LOGIN_SUCCESS
```

### Refresh Token Rotation

```
1. POST /auth/refresh { refresh_token }
   → hash token, lookup in DB
   → if revoked → REUSE DETECTED → kill session + all tokens
   → if expired → InvalidRefreshTokenError
   → if session expired/inactive → InvalidSessionError
   → create new RefreshToken
   → revoke old token (rotated_to_id = new.id)
   → touch session.last_used_at
   → create new access_token
   → audit: REFRESH
```

### OAuth Login (Google)

```
1. POST /auth/oauth/login { provider: "google", provider_token: "ya29..." }
   → GET https://oauth2.googleapis.com/tokeninfo?id_token=...
   → validate aud matches GOOGLE_OAUTH_CLIENT_ID
   → extract sub, email, name, picture

2. If OAuthAccount exists for (google, sub) → login existing user
3. Else if User with email exists → create OAuthAccount linked to existing user
4. Else → create User + OAuthAccount (auto-registered)
   → create session + tokens
   → audit: OAUTH_LOGIN
```
