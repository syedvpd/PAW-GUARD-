# Outbox Module

Transactional outbox pattern for reliable background job dispatch — ensures email/notification jobs are never lost if the worker is down.

---

## Architecture

```
outbox/
  service.py         # OutboxService (event persistence + polling)
  models.py          # OutboxEvent model
```

## Model

| Model | Table | Purpose |
|-------|-------|---------|
| `OutboxEvent` | `outbox_events` | Pending background job: payload, status, retry count |

## Flow

```
1. Domain service writes business event + OutboxEvent in SAME transaction
   -> Atomic: either both commit or neither does

2. Outbox poller (every 2 seconds) picks up PENDING events
   -> Enqueues to ARQ worker pool
   -> Marks event as DISPATCHED

3. ARQ worker executes the job
   -> On success: marks COMPLETED
   -> On failure: increments retry_count, requeues (max retries)
   -> After max retries: marks FAILED
```

## Purpose

The outbox pattern solves the dual-write problem: if a service sends an email via ARQ *after* committing the DB transaction, the email job could be lost if the worker crashes. The outbox ensures the job is persisted within the same transaction as the business event.

## Used By

- Email delivery (`send_notification_email_job`)
- Password reset emails
- Email verification emails
