# Secrets Management

## Overview

PawGuard manages sensitive configuration through environment variables and file-based secrets. No secrets are committed to the repository.

## Secret Categories

### JWT Keys (RS256)

**Generation:**
```bash
openssl genrsa -out secrets/private_key.pem 2048
openssl rsa -in secrets/private_key.pem -pubout -out secrets/public_key.pem
```

**Loading Priority:**
1. Environment variables (`JWT_PRIVATE_KEY_PEM`, `JWT_PUBLIC_KEY_PEM`)
2. File paths (`JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`)

**Note**: Environment variables take precedence. In hosted environments (Render), set PEM contents directly via env vars. Literal `\n` escapes are accepted.

### MFA Encryption Key

**Purpose**: Encrypts TOTP secrets at rest using Fernet symmetric encryption.

**Default Behavior**: When unset, key is derived from JWT private key.

**Production Recommendation**: Set independent `MFA_ENCRYPTION_KEY` so rotating JWT keypair does not orphan stored MFA secrets.

**Generation:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### OAuth Client IDs

```bash
GOOGLE_OAUTH_CLIENT_ID=<your-google-client-id>
APPLE_OAUTH_CLIENT_ID=<your-apple-client-id>
```

**Security**: OAuth login fails closed when unset - tokens with non-matching audience are rejected.

### Database Credentials

```bash
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database
```

**Never commit live credentials.** Use platform secret managers in production.

### Redis

```bash
REDIS_URL=redis://localhost:6379/0
```

### S3/Storage Credentials

```bash
S3_BUCKET_NAME=pawguard-media
S3_REGION=us-east-1
S3_ENDPOINT_URL=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

### Email (Brevo)

```bash
MAIL_FROM=no-reply@pawguard.org
BREVO_API_KEY=xkeysib-...
```

### Firebase Cloud Messaging

```bash
FCM_CREDENTIALS_PATH=path/to/service-account.json
```

When unset, push notifications silently degrade to in-app only.

### Payment Gateway (Razorpay)

```bash
PAYMENT_GATEWAY=razorpay
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
```

## File Structure

```
secrets/
  private_key.pem    # JWT private key (gitignored)
  public_key.pem     # JWT public key (gitignored)
```

## Environment Files

| File | Purpose | Committed |
|------|---------|-----------|
| `.env.example` | Template with placeholder values | Yes |
| `.env` | Local development secrets | No (gitignored) |

## Production Secrets

In production environments (Render, Docker):
- Use platform secret managers
- Set PEM contents directly in environment variables
- Do not mount `secrets/` directory

## Security Rules

1. Never commit secrets to version control
2. Never log secrets or tokens
3. Never expose secrets in API responses
4. Use environment variables for all sensitive configuration
5. Rotate keys periodically
6. Use independent MFA encryption key in production
