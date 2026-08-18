# Rate Limiting Implementation

## Overview

PawGuard uses a Redis-backed sliding window rate limiter for per-endpoint and per-user throttling. The implementation is in `src/pawguard/core/rate_limiter.py`.

## Architecture

### Sliding Window Counter
- Uses Redis `INCR` + `EXPIRE` commands
- Time-bucketed windows based on current timestamp
- Automatic key expiration after window + 1 second buffer

### Key Structure
```
rate_limit:{prefix}:{user_key}:{window_bucket}
```

Where:
- `prefix`: Endpoint identifier (e.g., "login", "register")
- `user_key`: Authenticated user ID or client IP address
- `window_bucket`: `int(time.time()) // window_seconds`

## Client IP Resolution

```python
def resolve_client_ip(request: Request) -> str:
    # 1. Cloudflare: CF-Connecting-IP
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # 2. Proxy: rightmost X-Forwarded-For entry
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]

    # 3. Direct connection
    return request.client.host
```

## User Key Resolution

```python
def _resolve_user_key(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        return str(user_id)  # Authenticated users: rate limit by user ID
    return resolve_client_ip(request)  # Anonymous: rate limit by IP
```

## Dependency Usage

```python
from pawguard.core.rate_limiter import rate_limit

@router.post("/login")
async def login(
    _: Annotated[None, Depends(rate_limit("login", 10, 60))],
    # ...
):
    ...
```

## Configured Rate Limits

| Endpoint | Prefix | Max Requests | Window |
|----------|--------|--------------|--------|
| Registration | `register` | 5 | 3600s (1 hour) |
| Login | `login` | 10 | 60s (1 minute) |
| Token Refresh | `refresh` | 30 | 60s (1 minute) |
| Password Reset Request | `password_reset` | 5 | 3600s (1 hour) |
| Password Reset Confirm | `password_reset_confirm` | 10 | 300s (5 minutes) |
| MFA Verify | `mfa_verify` | 10 | 300s (5 minutes) |
| MFA Enroll Confirm | `mfa_enroll_confirm` | 10 | 300s (5 minutes) |
| MFA Disable | `mfa_disable` | 10 | 300s (5 minutes) |
| Email Verify Request | `email_verify_request` | 10 | 300s (5 minutes) |
| Email Verify Confirm | `email_verify_confirm` | 10 | 300s (5 minutes) |
| Password Change | `password_change` | 10 | 300s (5 minutes) |
| OAuth Login | `oauth_login` | 10 | 60s (1 minute) |

## Configuration

Rate limiting can be disabled via environment variable:
```bash
RATE_LIMITING_ENABLED=true
```

When disabled, the rate limiter dependency returns immediately without checking Redis.

## Error Response

When rate limit exceeded:
```json
{
    "success": false,
    "data": null,
    "message": "Too many requests. Please try again later.",
    "errors": []
}
```

HTTP Status: `429 Too Many Requests`

## Security Considerations

1. **Header Spoofing Prevention**: IP resolution trusts only `CF-Returning-IP` (Cloudflare) and rightmost `X-Forwarded-For` (proxy chain)
2. **User-Based Limiting**: Authenticated requests rate-limited by user ID, not IP, preventing distributed attacks across IPs
3. **Separate Limits**: Sensitive endpoints (MFA, password reset) have independent, tighter limits
4. **Window Overlap**: Buffer period (`window_seconds + 1`) prevents edge-case bypass at window boundaries
