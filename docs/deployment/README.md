# Deployment Overview

## Architecture

PawGuard backend is deployed as a containerized application with the following components:

```
                    +-----------------+
                    |   Load Balancer |
                    +--------+--------+
                             |
                    +--------v--------+
                    |   API Server    |
                    |   (FastAPI)     |
                    +--------+--------+
                             |
              +--------------+--------------+
              |              |              |
    +---------v----+  +-----v------+  +---v--------+
    |  PostgreSQL  |  |   Redis    |  |  ARQ Worker |
    |  (Supabase)  |  |            |  |             |
    +--------------+  +------------+  +-------------+
```

## Services

### API Server
- FastAPI application
- Uvicorn ASGI server
- Port: 8000
- Health checks: `/health`, `/live`, `/ready`

### ARQ Worker
- Background job processor
- Email sending, notifications, reports
- Scheduled tasks

### PostgreSQL
- Primary data store
- Managed via Supabase
- Connection pooling via asyncpg

### Redis
- Caching layer
- Rate limiting
- Real-time events (Pub/Sub)
- Job queue backend

## Environment Configuration

### Required Variables

```bash
# Application
ENVIRONMENT=production
DEBUG=false

# Database
DATABASE_URL=postgresql+asyncpg://...

# Redis
REDIS_URL=redis://...

# JWT
JWT_PRIVATE_KEY_PEM=-----BEGIN RSA PRIVATE KEY-----...
JWT_PUBLIC_KEY_PEM=-----BEGIN PUBLIC KEY-----...

# MFA
MFA_ENCRYPTION_KEY=<fernet-key>

# OAuth
GOOGLE_OAUTH_CLIENT_ID=...
APPLE_OAUTH_CLIENT_ID=...
```

### Optional Variables

```bash
# S3 Storage
S3_BUCKET_NAME=pawguard-media
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# Email
BREVO_API_KEY=xkeysib-...

# Firebase
FCM_CREDENTIALS_PATH=path/to/credentials.json

# Payments
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
```

## Docker

### Dockerfile
- Base: `python:3.13-slim`
- Package manager: `uv`
- Multi-stage build
- Non-root user

### Docker Compose (Development)
```yaml
services:
  api:
    ports: ["8000:8000"]
    command: uvicorn pawguard.main:app --reload
  worker:
    command: arq pawguard.workers.arq_worker.WorkerSettings
```

### Docker Compose (Production)
```yaml
services:
  api:
    ports: ["8000:8000"]
    command: uvicorn pawguard.main:app --host 0.0.0.0 --port 8000
  worker:
    command: arq pawguard.workers.arq_worker.WorkerSettings
```

## Health Checks

### GET /health
```json
{"data": {"status": "ok"}}
```

### GET /live
```json
{"data": {"status": "alive"}}
```

### GET /ready
```json
{
  "data": {
    "database": "ok",
    "redis": "ok"
  }
}
```

## Metrics

### GET /metrics
Prometheus-compatible metrics endpoint:
- Request rate, latency, errors (RED)
- Database pool metrics
- Redis connection metrics
- Worker queue depth

## Migration Strategy

1. Run Alembic migrations on startup
2. Idempotent role/permission reconciliation
3. Backfill default role for legacy users

```python
async def _seed_roles():
    from scripts.seed_roles_and_permissions import reconcile_roles, backfill_default_role
    async with AsyncSessionLocal() as session:
        await reconcile_roles(session, verbose=False)
        await backfill_default_role(session, verbose=False)
        await session.commit()
```

## Deployment Platforms

### Render
- See [render.md](render.md) for specifics

### Docker
- See `docker-compose.yml` and `Dockerfile`

### Manual
- Install dependencies: `uv pip install --system .`
- Run migrations: `alembic upgrade head`
- Start server: `uvicorn pawguard.main:app`

## Security Checklist

- [ ] Environment variables set (no hardcoded secrets)
- [ ] HTTPS enabled
- [ ] CORS origins configured
- [ ] Trusted hosts configured
- [ ] Rate limiting enabled
- [ ] JWT keys generated and set
- [ ] MFA encryption key set
- [ ] Database SSL enabled
- [ ] Redis password set (if exposed)
- [ ] S3 bucket private
- [ ] Firebase credentials secured
