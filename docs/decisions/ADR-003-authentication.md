# ADR-003: Authentication

## Status

Accepted

## Context

PawGuard requires a secure authentication system supporting:
- Multiple client types (web, mobile, admin)
- Multi-factor authentication
- Session management
- Role-based access control
- OAuth social login

## Decision

Use **JWT RS256** for access tokens with **opaque refresh tokens** and **TOTP MFA**.

## Alternatives Considered

### Session-based (server-side)
- **Pros**: Simple, server-controlled expiry
- **Cons**: Stateful, harder to scale, CSRF vulnerabilities
- **Verdict**: Rejected for stateless scalability

### JWT HS256 (symmetric)
- **Pros**: Simpler setup, faster signing
- **Cons**: Same key for signing/verification, less secure for distributed systems
- **Verdict**: Rejected in favor of asymmetric RS256

### OAuth 2.0 with third-party provider only
- **Pros**: Delegated authentication
- **Cons**: Vendor lock-in, requires internet, less control
- **Verdict**: Rejected as sole auth method (used as supplement)

### Passkeys/WebAuthn
- **Pros**: Phishing-resistant, modern
- **Cons**: Limited browser support, complex setup
- **Verdict**: Considered for future implementation

## Consequences

### Positive
- Stateless access tokens (scalable)
- Asymmetric signing (public key for verification)
- Refresh token rotation with reuse detection
- TOTP MFA with encrypted secrets
- Session management with device tracking
- OAuth support for social login

### Negative
- Token revocation requires黑名单 (handled via session table)
- More complex than session-based
- JWT payload visible (no sensitive data in claims)

## Implementation Details

### Token Structure
```python
# Access Token (RS256)
{
    "sub": "user_id",
    "sid": "session_id",
    "roles": ["role1", "role2"],
    "type": "access",
    "jti": "unique_token_id",
    "iat": "issued_at",
    "exp": "expires_at"
}
```

### Password Hashing
- Argon2id with OWASP parameters (19 MiB, t=2, p=1)
- Automatic rehashing on parameter changes

### MFA
- TOTP with 30-second window
- Fernet encryption at rest
- Mandatory for admin users

### Refresh Token Rotation
- Opaque 48-byte tokens
- SHA-256 hashed in database
- Rotation on every use
- Reuse detection triggers session revocation

### Session Management
- Device tracking (ID, name, type, IP, user agent)
- Inactivity timeout (30 days)
- Individual and global revocation

## Security Features

1. Account lockout after 5 failed attempts
2. Rate limiting on auth endpoints
3. CSRF protection via SameSite cookies
4. Secure cookie flags (HttpOnly, Secure, SameSite)
5. OAuth audience validation
6. Audit logging for all auth events
