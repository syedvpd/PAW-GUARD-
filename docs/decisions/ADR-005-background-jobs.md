# ADR-005: Background Jobs

## Status

Accepted

## Context

PawGuard requires background processing for:
- Email sending (verification, password reset, notifications)
- Push notifications (FCM)
- Report generation (PDF, Excel)
- Scheduled tasks (cron jobs)
- Async webhooks

## Decision

Use **ARQ** (Async Redis Queue) for background job processing.

## Alternatives Considered

### Celery
- **Pros**: Mature, feature-rich, large ecosystem
- **Cons**: Heavy dependency, complex setup, Redis/RabbitMQ required
- **Verdict**: Rejected due to complexity and overhead

### Huey
- **Pros**: Simple, lightweight
- **Cons**: Less async support, smaller community
- **Verdict**: Rejected in favor of ARQ's async-native design

### FastAPI BackgroundTasks
- **Pros**: Built-in, simple
- **Cons**: Not persistent, lost on restart, no retry
- **Verdict**: Rejected for critical operations

### RQ (Redis Queue)
- **Pros**: Simple, Redis-based
- **Cons**: Synchronous, not async-native
- **Verdict**: Rejected in favor of ARQ

## Consequences

### Positive
- Async-native (Python asyncio)
- Redis-based (already using Redis)
- Simple setup and configuration
- Job retry with backoff
- Scheduled/cron jobs
- Worker pools

### Negative
- Redis dependency (single point of failure)
- Less mature than Celery
- Limited monitoring UI

## Implementation

### Worker Configuration
```python
# src/pawguard/workers/arq_worker.py
class WorkerSettings:
    functions = [
        "pawguard.workers.jobs...function_name",
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
```

### Worker Pool
```python
# src/pawguard/workers/pool.py
# Manages ARQ Redis connection pool
# Used by services to enqueue jobs
```

### Job Types

#### Email Jobs
- `send_email_verification_email_job`
- `send_password_reset_email_job`
- `send_notification_email_job`

#### Notification Jobs
- Push notifications via FCM
- In-app notifications

#### Report Jobs
- PDF generation
- Excel export
- CSV export

#### Scheduled Jobs
- Cron-based task execution
- Maintenance tasks

### Outbox Pattern
```python
# src/pawguard/modules/outbox/service.py
# Transactions write events to outbox table
# Background worker polls and processes events
# Ensures exactly-once delivery
```

### Job Retry
```python
# src/pawguard/workers/jobs/retry.py
# Exponential backoff
# Configurable max retries
# Dead letter queue for failed jobs
```

## Docker Compose

```yaml
worker:
  build:
    context: .
    dockerfile: Dockerfile
  command: arq pawguard.workers.arq_worker.WorkerSettings
  env_file:
    - .env
```

## Monitoring

- Worker health checks
- Job success/failure metrics
- Queue depth monitoring
- Structured logging for job execution

## Error Handling

- Failed jobs retried with backoff
- Dead letter queue for persistent failures
- Structured error logging
- Alert on repeated failures
