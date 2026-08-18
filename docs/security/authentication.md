# JWT Authentication Implementation

## Overview

PawGuard implements a custom JWT-based authentication system using RS256 asymmetric signing. The implementation is split between cryptographic primitives (`core/security.py`) and business logic (`modules/auth/service.py`).

## Token Types

### Access Token
- **Algorithm**: RS256 (RSA Signature with SHA-256)
- **Default Expiry**: 15 minutes
- **Claims**: `sub` (user_id), `sid` (session_id), `roles`, `type`, `jti`, `iat`, `exp`

### Pre-Auth Token
- **Purpose**: Bridges login to MFA verification step
- **Default Expiry**: 5 minutes
- **Claims**: `sub` (user_id), `sid` (session_id), `type`, `jti`, `iat`, `exp`

### Refresh Token
- **Storage**: Opaque 48-byte URL-safe token, SHA-256 hashed in database
- **Default Expiry**: 30 days
- **Rotation**: Rotated on every use with reuse detection

## Authentication Flow

```
1. Client sends POST /auth/login with email/password
2. Service verifies credentials against Argon2id hash
3. If MFA enabled:
   a. Returns pre-auth token (short-lived)
   b. Client sends POST /auth/mfa/verify with pre-auth token + TOTP code
   c. Service validates TOTP and returns access + refresh tokens
4. If MFA not enabled:
   a. Returns access + refresh tokens directly
5. For web clients: tokens set as httponly, secure, samesite=strict cookies
6. For mobile clients: tokens returned in response body
```

## Password Hashing

```python
# Argon2id with OWASP-recommended low-cost profile
_password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19_456,  # 19 MiB
    parallelism=1
)
```

- Automatic rehashing when cost parameters change (checked on login)
- Rehashing piggybacks on existing UPDATE request (no extra DB round trip)

## Session Management

### Session Creation
- Recorded with device_id, device_name, device_type, IP, user agent
- Session expiry aligned with refresh token expiry
- Inactivity timeout: 30 days (`SESSION_INACTIVITY_TIMEOUT_DAYS`)

### Session Revocation
- Individual session revocation via `DELETE /auth/sessions/{session_id}`
- Global revocation via `POST /auth/logout-all`
- Automatic revocation on password change/reset
- Automatic revocation on refresh token reuse detection

## Refresh Token Rotation

```
1. Client sends POST /auth/refresh with refresh token
2. Service validates token hash against database
3. If token is revoked: possible reuse attack
   a. Revoke entire session
   b. Revoke all refresh tokens for session
   c. Log REFRESH_REUSE_DETECTED audit event
4. If valid: issue new refresh token, revoke old one
5. Link old token to new via rotated_to_id
```

## MFA (TOTP)

### Enrollment
```
1. POST /auth/mfa/enroll - generates secret, returns provisioning URI
2. User scans QR code in authenticator app
3. POST /auth/mfa/enroll/confirm with TOTP code
4. Secret encrypted with Fernet before database storage
5. mfa_enabled flag set to true
```

### Verification
- TOTP verification with `valid_window=1` (30-second tolerance)
- Legacy plaintext secrets transparently re-encrypted on verification

### Mandatory MFA for Admins
- Configurable via `MFA_MANDATORY_FOR_ADMINS` setting
- Admin users without MFA enrolled cannot complete login
- Admin users cannot disable MFA

## OAuth Social Login

### Supported Providers
- Google (ID token verification via `oauth2.googleapis.com/tokeninfo`)
- Apple (JWT verification with Apple public keys)

### Security Measures
- Audience validation (prevents cross-app token confusion)
- Email verification check for Google
- Token never stored in database (verified on every login)
- Account linking/unlinking with conflict detection

## Account Security

### Failed Login Protection
- Account locked after 5 failed attempts (`MAX_FAILED_LOGIN_ATTEMPTS`)
- Lockout duration: 15 minutes (`ACCOUNT_LOCKOUT_MINUTES`)
- Failed count reset on successful login

### Password Change
- Requires current password verification
- Revokes all other sessions after change
- Audit logged with actor information

## Cookie Configuration (Web Clients)

```python
response.set_cookie(
    "access_token",
    access_token,
    max_age=access_token_expire_minutes * 60,
    httponly=True,
    secure=settings.cookie_secure,
    samesite="strict",
    domain=cookie_domain,
)
```

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/auth/register` | 5 | 3600s |
| `/auth/login` | 10 | 60s |
| `/auth/refresh` | 30 | 60s |
| `/auth/password/reset/request` | 5 | 3600s |
| `/auth/mfa/verify` | 10 | 300s |
| `/auth/oauth/login` | 10 | 60s |
