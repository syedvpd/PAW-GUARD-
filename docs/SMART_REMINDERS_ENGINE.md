# Smart Reminders Engine — Vaccination Schedules & Medication Push Notifications

An automated reminder engine that turns pet vaccination/medication schedules into
on-time push notifications, without blocking any HTTP request.

## Architecture

```
Pet reminder (DB row)                 ARQ cron (daily 09:45)
   │                                     │
   └─ source_key (idempotent)            ▼
                              send_companion_pet_reminders
                                         │
                                   due-within-48h scan
                                         │
                            NotificationService (in-app)
                                         │
                                  (per-recipient delivery)
```

Reminders are **created** by the owner (or a vet via the appointments flow) through
the API. **Delivery** is fully asynchronous, handled by the ARQ background worker
so the HTTP request stays fast (per AGENTS.md: long-running work in background).

## Data model

`pet_reminders` (migration `a0b1c2d3e4f5`):
- `pet_id` FK → `companion_pets`
- `owner_id` FK → `users`
- `kind` ∈ `vaccination` | `medication` (`ReminderKind`)
- `title`, `details`, `due_at` (timestamptz)
- `source_key` (string) — **idempotency key**
- `is_active` boolean
- `UNIQUE (pet_id, source_key)` — prevents duplicate reminders for the same pet
- soft-delete (`deleted_at`)

## API

| Method | Path | Permission | Notes |
|--------|------|------------|-------|
| POST | `/companion-pets/{pet_id}/reminders` | `companion_pet:update` | create |
| GET | `/companion-pets/{pet_id}/reminders` | `companion_pet:read` | list |
| DELETE | `/companion-pets/{pet_id}/reminders/{reminder_id}` | `companion_pet:update` | soft delete |

`PetReminderCreate`:
```json
{
  "kind": "vaccination",
  "title": "Rabies booster due",
  "details": "Annual rabies vaccination",
  "due_at": "2026-09-01T09:00:00Z",
  "source_key": "vet-clinic-42:rabies-2026"
}
```

## Delivery worker

`send_companion_pet_reminders` (`src/pawguard/workers/jobs/companion_pet_jobs.py`):
1. Selects active reminders whose `due_at` is within the next 48 hours and that
   have not yet been delivered (tracked via the notification delivery key).
2. For each reminder, pushes an in-app notification to the owner via
   `NotificationService`, with a unique delivery `source_key` so ARQ retries are
   **idempotent** (no duplicate notifications on retry).
3. Confirms delivery and updates reminder tracking.
4. Registered in `WorkerSettings.functions` and scheduled by cron:
   `cron(send_companion_pet_reminders, hour={9}, minute={45}, max_tries=2)`.
5. Wrapped by the `_track_failures` decorator so every job failure increments the
   `arq_job_failed_total` metric and is logged with the job id/try/args.

## Why push notifications won't block requests

- Reminder *creation* (the HTTP call) only writes the DB row and returns 201.
- All notification delivery happens **after the HTTP response**, in the worker.
- Per the transaction rules, no notification/IO is performed inside a DB
  transaction; the worker commits the reminder read, then dispatches
  notifications.

## Channels

Today the engine delivers via the in-app `NotificationService` (the existing
notification table + unread-count API). The engine is channel-pluggable: email jobs
and SMS push can be added to the same ARQ schedule without touching the reminder
model — the worker already separates the "what is due" concern from the "how to
notify" concern.

## Test plan (manual)

1. `POST /companion-pets/{pet_id}/reminders` with `due_at` ≈ now + 1h (201).
2. `GET /companion-pets/{pet_id}/reminders` (200, reminder listed).
3. Trigger delivery manually:
   `python -c "import asyncio; from pawguard.workers.jobs.companion_pet_jobs import send_companion_pet_reminders; asyncio.run(send_companion_pet_reminders({}))"`
4. `GET /notifications` for the owner → confirm a vaccination/medication
   reminder notification exists.
5. Re-run step 3 → confirm no duplicate notification (idempotency).
6. `DELETE /companion-pets/{pet_id}/reminders/{reminder_id}` (200), then GET →
   reminder absent.