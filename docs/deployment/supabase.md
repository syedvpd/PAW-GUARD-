# Supabase Database Setup

## Overview

Supabase provides managed PostgreSQL hosting with additional features. This document covers setup and configuration for PawGuard.

## Project Setup

### 1. Create Supabase Project
1. Go to [supabase.com](https://supabase.com)
2. Sign up/log in
3. Create new project
4. Choose region (closest to users)
5. Set database password

### 2. Get Connection String
1. Go to Settings -> Database
2. Copy connection string
3. Use "Transaction" mode for SQLAlchemy

```
postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
```

### 3. Configure Backend
```bash
DATABASE_URL=postgresql+asyncpg://postgres.xxxx:password@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
```

**Note**: The backend normalizes `postgresql://` to `postgresql+asyncpg://` automatically.

## Schema Management

### Alembic Migrations
- Migrations stored in `alembic/versions/`
- Run automatically on application startup
- Idempotent reconciliation for roles/permissions

### Manual Migration
```bash
alembic upgrade head
```

### Migration Files
- Version-controlled in Git
- Timestamped for ordering
- Reversible (up/down)

## Row-Level Security (RLS)

### Optional Implementation
Supabase supports RLS, but PawGuard handles authorization at the application level via RBAC.

### Enabling RLS
If RLS is desired:
1. Enable on tables via Supabase dashboard
2. Create policies based on `auth.uid()` or JWT claims
3. Test thoroughly before production

## Real-Time Subscriptions

### Dispatch Events
PawGuard uses Redis Pub/Sub for real-time dispatch updates, but Supabase real-time can be used as an alternative:

```javascript
// Frontend subscription
supabase
  .channel('rescue-updates')
  .on('postgres_changes', { event: '*', schema: 'public', table: 'rescue_requests' }, payload => {
    console.log('Change received!', payload)
  })
  .subscribe()
```

## Storage

### Supabase Storage
PawGuard can use Supabase Storage for file uploads:

1. Create buckets in Supabase dashboard
2. Set bucket policies (public/private)
3. Configure backend to use Supabase Storage URL

### Bucket Structure
```
pawguard-media/
  dogs/
    {dog-id}/
      photos/
      videos/
  rescue/
    {rescue-id}/
      evidence/
  users/
    {user-id}/
      profile/
```

## Database Backups

### Automatic Backups
- Supabase provides daily backups (paid plans)
- Point-in-time recovery available

### Manual Backup
```bash
pg_dump $DATABASE_URL > backup.sql
```

### Restore
```bash
psql $DATABASE_URL < backup.sql
```

## Monitoring

### Supabase Dashboard
- Database metrics
- Query performance
- Connection pool stats

### External Monitoring
- Use `/ready` endpoint for health checks
- Monitor connection pool via `/metrics`

## Security

### Database Password
- Use strong password
- Rotate periodically
- Store in environment variables

### SSL Connections
- Supabase enforces SSL
- Connection string includes `sslmode=require`

### IP Allowlisting
- Restrict to known IPs in production
- Supabase dashboard -> Settings -> Database -> Network restrictions

## Performance

### Connection Pooling
Supabase provides connection pooling via PgBouncer:
- Transaction mode (recommended for asyncpg)
- Connection limit: Check Supabase plan

### Indexes
PawGuard includes performance indexes in migrations:
- Composite indexes for common queries
- Partial indexes for filtered queries
- Index monitoring via `pg_stat_user_indexes`

### Query Optimization
- Use EXPLAIN ANALYZE for slow queries
- Monitor `pg_stat_statements`
- Supabase dashboard -> SQL Editor -> Query Performance

## Cost

### Free Tier
- 500MB database
- 1GB file storage
- 50,000 monthly active users
- Good for development/testing

### Pro Plan ($25/month)
- 8GB database
- 100GB file storage
- Unlimited active users
- Daily backups
- Recommended for production

## Troubleshooting

### Connection Issues
1. Check connection string format
2. Verify password
3. Check IP allowlist
4. Verify project is active

### Migration Issues
1. Check Alembic version table
2. Verify migration files
3. Check for conflicting migrations

### Performance Issues
1. Check query execution plans
2. Verify indexes exist
3. Monitor connection pool
4. Check for N+1 queries
