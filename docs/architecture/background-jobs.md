# Background Job Architecture

Scope: ARQ worker, transactional outbox pattern, scheduled jobs, retry strategy, and job monitoring.

---

## 1. Job Queue Architecture

### ARQ Worker

The background job system uses ARQ (Async Redis Queue) with Redis as the message broker.

```
+------------------+     +------------------+
|  API Container   |     | Worker Container |
|                  |     |                  |
| Service Layer    |     | ARQ Worker       |
|     |            |     |     |            |
|     v            |     |     v            |
| OutboxService    |     | Job Functions    |
| .enqueue_job()   |     | Scheduled Cron   |
|     |            |     | Outbox Poller    |
|     v            |     |     |            |
| PostgreSQL       |     |     v            |
| (outbox_events)  |     | Redis Queue      |
+------------------+     +------------------+
         |                       |
         +----------+------------+
                    |
                    v
            +---------------+
            | Background    |
            | Job Execution |
            +---------------+
```

### Container Configuration

| Container | Command | Purpose |
|-----------|---------|---------|
| `api` | `uvicorn pawguard.main:app` | Serves HTTP + outbox enqueue |
| `worker` | `arq pawguard.workers.arq_worker.WorkerSettings` | Processes jobs + cron |

Source: `docker-compose.yml:17-26`

---

## 2. Transactional Outbox Pattern

### Problem

Background jobs (email, push notifications) must be reliably dispatched, but:
- Sending emails inside a database transaction violates TRANSACTION RULES
- Enqueuing to Redis before commit risks job execution before data is committed
- Network failures between DB commit and Redis enqueue lose jobs

### Solution

The Transactional Outbox pattern ensures atomic job enqueueing:

```
1. Service writes job event to outbox_events table (same transaction as business data)
2. Transaction commits (business data + outbox event are atomic)
3. Outbox poller (in worker) picks up pending events
4. Poller enqueues jobs to ARQ Redis queue
5. ARQ worker processes jobs
6. Outbox event marked as completed
```

### OutboxEvent Model

```python
class OutboxEvent(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "outbox_events"

    job_name: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

### OutboxService

```python
class OutboxService:
    @staticmethod
    async def enqueue_job(session: AsyncSession, job_name: str, **payload) -> OutboxEvent:
        """Save pending job event within active transaction."""
        event = OutboxEvent(job_name=job_name, payload=payload, status="pending", retry_count=0)
        session.add(event)
        await session.flush()
        return event
```

### Concurrency-Safe Polling

The poller uses `SELECT ... FOR UPDATE SKIP LOCKED` to prevent duplicate processing:

```python
stmt = (
    select(OutboxEvent)
    .where(OutboxEvent.status == "pending")
    .order_by(OutboxEvent.created_at.asc())
    .limit(batch_size)
    .with_for_update(skip_locked=True)
)
```

### Processing States

| State | Description |
|-------|-------------|
| `pending` | Ready for processing |
| `processing` | Currently being processed |
| `completed` | Successfully dispatched to ARQ |
| `failed` | Permanently failed (retry_count >= 5) |

Source: `src/pawguard/modules/outbox/service.py:1-92`

---

## 3. Worker Configuration

### WorkerSettings

```python
class WorkerSettings:
    max_tries = 5
    functions: list[Any] = [
        _send_password_reset_email_job,
        _send_email_verification_email_job,
        _send_notification_email_job,
        _check_inventory_low_stock,
        _check_inventory_expiry,
        _check_vaccination_renewals,
        _post_adoption_followups,
        _process_sponsorship_charges,
        _send_companion_pet_reminders,
        _broadcast_lost_pet_alert,
    ]
    cron_jobs = [
        cron(_check_inventory_low_stock, hour={0, 12}, minute={0}, max_tries=2),
        cron(_check_inventory_expiry, hour={9}, minute={0}, max_tries=2),
        cron(_check_vaccination_renewals, hour={9, minute={30}, max_tries=2),
        cron(_post_adoption_followups, hour={10}, minute={0}, max_tries=2),
        cron(_process_sponsorship_charges, hour={8}, minute={0}, max_tries=2),
        cron(_send_companion_pet_reminders, hour={9, minute={45}, max_tries=2),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
```

Source: `src/pawguard/workers/arq_worker.py:130-157`

---

## 4. Job Types

### On-Demand Jobs

Enqueued by services during request processing:

| Job | Source | Trigger |
|-----|--------|---------|
| `send_password_reset_email_job` | `auth/service.py` | Password reset request |
| `send_email_verification_email_job` | `auth/service.py` | Email verification request |
| `send_notification_email_job` | `notifications/service.py` | Notification with `send_email=True` |
| `broadcast_lost_pet_alert` | `lost_found/service.py` | Lost pet report created |

### Scheduled Cron Jobs

| Job | Schedule | Purpose |
|-----|----------|---------|
| `check_inventory_low_stock` | 00:00, 12:00 daily | Alert staff when items below threshold |
| `check_inventory_expiry` | 09:00 daily | Alert staff when items expire within 60 days |
| `check_vaccination_renewals` | 09:30 daily | Remind staff of vaccinations due in 14 days |
| `post_adoption_followups` | 10:00 daily | Send follow-up prompts at 30/90/180 days |
| `process_sponsorship_charges` | 08:00 daily | Charge monthly sponsorships |
| `send_companion_pet_reminders` | 09:45 daily | Send companion pet reminders |

### Outbox Polling

The outbox poller runs as a background task within the worker process:

```python
async def outbox_poller_loop(ctx: dict[str, Any]) -> None:
    while True:
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    processed = await OutboxService.process_pending_events(session, pool)
        except Exception as e:
            logger.error("outbox_poller_loop_error", error=str(e))
        await asyncio.sleep(2)  # Poll every 2 seconds
```

Source: `src/pawguard/workers/arq_worker.py:79-97`

---

## 5. Retry Strategy

### Email Job Retries

Email jobs distinguish between permanent and transient failures:

| Failure Type | Examples | Behavior |
|-------------|---------|----------|
| Permanent | `SMTPAuthenticationError`, `SMTPSenderRefused`, `SMTPRecipientsRefused` | Fail immediately, no retry |
| Transient | `TimeoutError`, `ConnectionError`, `SMTPException`, `URLError` | Retry with backoff |

### Retry Backoff

```python
# From workers/jobs/retry.py
def retry_defer(ctx: dict[str, Any]) -> int:
    """Calculate retry delay with exponential backoff."""
    attempt = ctx.get("job_try", 0)
    return min(2 ** attempt * 30, 3600)  # 30s, 60s, 120s, ... max 1h
```

### Max Retries

| Job Type | Max Tries | Rationale |
|----------|-----------|-----------|
| Email jobs | 5 | Transient SMTP failures usually resolve quickly |
| Scheduled cron jobs | 2 | Missed runs fire again on next cycle |

### Worker-Level Retry Tracking

Every job is wrapped with `_track_failures` which instruments:

| Metric | Labels | Description |
|--------|--------|-------------|
| `worker_jobs_total` | `job`, `status` | Job execution count by status |
| `worker_job_duration_ms` | `job` | Job execution latency |
| `worker_job_retries_total` | `job` | Retry count |
| `worker_job_failures_total` | `job` | Permanent failure count |
| `arq_job_failed_total` | `job` | ARQ-level failure count |

Source: `src/pawguard/workers/arq_worker.py:37-76`

---

## 6. Worker Lifecycle

### Startup

```python
async def startup(ctx: dict[str, object]) -> None:
    configure_logging()
    logger.info("arq_worker_startup", max_tries=WorkerSettings.max_tries)
    ctx["outbox_task"] = asyncio.create_task(outbox_poller_loop(ctx))
```

### Shutdown

```python
async def shutdown(ctx: dict[str, object]) -> None:
    logger.info("arq_worker_shutdown")
    task = ctx.get("outbox_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
```

### ARQ Pool (API Side)

The API container uses a separate Redis pool for enqueuing jobs:

```python
class _SafeArqPool:
    """Wrapper that traps connection errors during enqueue_job."""
    async def enqueue_job(self, *args, **kwargs) -> Any:
        try:
            return await self._inner.enqueue_job(*args, **kwargs)
        except Exception as exc:
            logger.warning("arq_pool_enqueue_failed_falling_back", error=str(exc))
            return None
```

When Redis is unreachable, the pool degrades to `_NullArqPool` which logs warnings and drops jobs.

Source: `src/pawguard/workers/pool.py:1-65`

---

## 7. Job Definitions

### Email Jobs

**Source:** `workers/jobs/email_jobs.py`

| Job Function | Template | Subject |
|-------------|----------|---------|
| `send_password_reset_email_job` | `password_reset.html` | "Reset your PawGuard password" |
| `send_email_verification_email_job` | `email_verification.html` | "Verify your PawGuard email" |
| `send_notification_email_job` | `notification.html` | Custom subject |

All email jobs use `asyncio.to_thread()` to run blocking SMTP calls in a worker thread.

### Scheduled Jobs

**Source:** `workers/jobs/scheduled_jobs.py`

| Job | Query | Action |
|-----|-------|--------|
| `check_inventory_low_stock` | Items where `quantity <= reorder_threshold` | In-app + push notification to staff |
| `check_inventory_expiry` | Items expiring within 60 days | In-app + push notification to staff |
| `check_vaccination_renewals` | Vaccinations due within 14 days | In-app + push notification to staff |
| `post_adoption_followups` | Adoptions completed 30/90/180 days ago | In-app + email + push to adopter |
| `process_sponsorship_charges` | Sponsorships with `next_charge_date <= today` | Create donation record, advance charge date |
| `send_companion_pet_reminders` | Companion pet due reminders | In-app + email + push to owner |

### Lost & Found Jobs

**Source:** `workers/jobs/lost_found_jobs.py`

| Job | Trigger | Action |
|-----|---------|--------|
| `broadcast_lost_pet_alert` | Lost pet report created | Push notification to nearby users |

---

## 8. Outbox Processing Flow

```
Service Request
    |
    v
[1] Begin database transaction
    |
    v
[2] Write business data (e.g., create adoption record)
    |
    v
[3] OutboxService.enqueue_job(session, "send_notification_email_job", ...)
    |
    v
[4] Commit transaction (business data + outbox event atomic)
    |
    v
[5] Outbox poller (every 2s) picks up pending event
    |
    v
[6] SELECT ... FOR UPDATE SKIP LOCKED (concurrency-safe)
    |
    v
[7] Mark event as "processing"
    |
    v
[8] Enqueue job to ARQ Redis queue
    |
    v
[9] Mark event as "completed"
    |
    v
[10] ARQ worker picks up job
    |
    v
[11] Execute job function (e.g., send email)
    |
    v
[12] Job completes (or retries on transient failure)
```

---

## 9. Error Handling in Jobs

### Transient Failures

```python
try:
    await asyncio.to_thread(EmailService().send, to=to, subject=subject, html_body=html_body)
except _TRANSIENT as exc:
    raise Retry(defer=retry_defer(ctx)) from exc
```

### Permanent Failures

```python
except _PERMANENT as exc:
    logger.error("email_send_failed", to=to, subject=subject, error=str(exc))
    raise  # No retry, logged as permanent failure
```

### Job Failure Tracking

All job failures are tracked via metrics and structured logging:

| Log Field | Description |
|-----------|-------------|
| `job` | Job function name |
| `job_id` | ARQ job identifier |
| `job_try` | Current attempt number |
| `error_type` | Exception class name |
| `error` | Exception message |

Source: `src/pawguard/workers/arq_worker.py:57-74`

---

## 10. Monitoring and Observability

### Worker Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `worker_jobs_total` | Counter | `job`, `status` | Job executions by status |
| `worker_job_duration_ms` | Histogram | `job` | Job execution latency |
| `worker_job_retries_total` | Counter | `job` | Retry count per job |
| `worker_job_failures_total` | Counter | `job` | Permanent failure count |
| `arq_job_failed_total` | Counter | `job` | ARQ-level failures |

### Health Indicators

| Indicator | Source | Threshold |
|-----------|--------|-----------|
| Outbox backlog | `outbox_events WHERE status = 'pending'` | Alert if > 100 |
| Failed jobs | `worker_job_failures_total` | Alert if increasing |
| Job latency | `worker_job_duration_ms` | Alert if p95 > 30s |
| Worker connectivity | `arq_pool_unreachable_falling_back_to_noop` log | Alert on occurrence |
