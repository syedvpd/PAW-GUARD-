# Render Deployment

## Overview

Render is the recommended deployment platform for PawGuard. This document covers deployment specifics.

## Services

### Web Service (API)
- **Type**: Web Service
- **Runtime**: Docker
- **Port**: 8000
- **Health Check Path**: `/health`

### Background Worker
- **Type**: Worker
- **Runtime**: Docker
- **Command**: `arq pawguard.workers.arq_worker.WorkerSettings`

### PostgreSQL
- **Type**: PostgreSQL
- **Plan**: Starter or higher
- **Note**: Use Supabase for production (see supabase.md)

### Redis
- **Type**: Redis
- **Plan**: Starter

## Environment Variables

Set all required environment variables in Render's dashboard:

### Database
```
DATABASE_URL=postgresql://user:password@host:port/database
```

### Redis
```
REDIS_URL=redis://red-xxxxx:xxxxx@redis-host:port
```

### JWT (Set via Environment Variables, not files)
```
JWT_PRIVATE_KEY_PEM=-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----
JWT_PUBLIC_KEY_PEM=-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----
```

**Note**: Use `\n` for newlines in PEM keys.

### Application
```
ENVIRONMENT=production
DEBUG=false
ALLOWED_HOSTS=your-app.onrender.com
CORS_ORIGINS=https://your-frontend.vercel.app
COOKIE_DOMAIN=your-app.onrender.com
COOKIE_SECURE=true
```

### OAuth
```
GOOGLE_OAUTH_CLIENT_ID=...
APPLE_OAUTH_CLIENT_ID=...
```

### Email
```
BREVO_API_KEY=xkeysib-...
MAIL_FROM=no-reply@pawguard.org
```

### Storage (Optional)
```
S3_BUCKET_NAME=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

## Docker Configuration

### Render-Specific Considerations

1. **No secrets/ directory**: Render doesn't have the `secrets/` directory. Use environment variables for JWT keys.

2. **Port binding**: Render provides the `PORT` environment variable. The Dockerfile uses port 8000, but Render maps it automatically.

3. **Build time**: First build may take 5-10 minutes for dependency installation.

4. **Free tier limitations**:
   - Spins down after inactivity
   - Limited CPU/RAM
   - Outbound SMTP blocked (use Brevo API instead)

## Deployment Steps

1. **Connect Repository**
   - Link GitHub repository
   - Select Dockerfile as build method

2. **Configure Services**
   - Create Web Service for API
   - Create Worker for background jobs
   - Add PostgreSQL (or connect Supabase)
   - Add Redis

3. **Set Environment Variables**
   - Copy from `.env.example`
   - Fill in production values
   - Set JWT keys as environment variables

4. **Deploy**
   - Trigger manual deploy
   - Monitor build logs
   - Verify health checks

## Post-Deployment

### Verify Health
```bash
curl https://your-app.onrender.com/health
```

### Check Logs
- Render dashboard -> Logs tab
- Monitor for errors

### Database Migrations
- Run automatically on startup via `_seed_roles()`
- Alembic migrations applied idempotently

## Scaling

### Vertical Scaling
- Upgrade service plan for more CPU/RAM
- Recommended: Starter ($7/month) minimum

### Horizontal Scaling
- Scale web service instances
- Single worker instance (ARQ doesn't support multi-worker well)

## Cost Optimization

### Free Tier
- Good for development/testing
- Spins down after 15 minutes of inactivity
- Limited to 750 hours/month

### Starter Plan
- Always-on
- Better performance
- Recommended for production

## Monitoring

### Render Dashboard
- Service metrics
- Log streaming
- Deploy history

### External Monitoring
- Health check endpoint
- Prometheus metrics at `/metrics`

## Troubleshooting

### Build Failures
- Check build logs
- Verify Dockerfile syntax
- Ensure all dependencies install

### Runtime Errors
- Check service logs
- Verify environment variables
- Check database connectivity

### Slow Performance
- Upgrade service plan
- Check database query performance
- Monitor Redis hit rate
