# Notifications Module

In-app notifications, Firebase Cloud Messaging (FCM) push notifications, email delivery, and user preferences.

---

## Architecture

```
notifications/
  router.py          # 12 endpoints
  service.py         # NotificationService + NotificationPreferenceService
  repository.py      # Data access
  models.py          # ORM models
  schemas.py         # Pydantic DTOs
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `Notification` | `notifications` | In-app notification: title, body, type, read status |
| `NotificationPreference` | `notification_preferences` | Per-user: enable_push, enable_email, quiet_hours |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/notifications` | Authenticated | List notifications (paginated) |
| GET | `/notifications/unread-count` | Authenticated | Unread count |
| PUT | `/notifications/{id}/read` | Authenticated | Mark single as read |
| PUT | `/notifications/read-all` | Authenticated | Mark all as read |
| DELETE | `/notifications/{id}` | Authenticated | Soft delete |
| POST | `/notifications/bulk/delete` | `notification:manage` | Bulk soft delete |
| POST | `/notifications/send` | `notification:manage` | Send notification (optional push + email) |
| GET | `/notifications/preferences` | Authenticated | Get preferences |
| PUT | `/notifications/preferences` | Authenticated | Update preferences |
| POST | `/notifications/broadcast` | `system:admin` | Broadcast to user IDs |
| POST | `/notifications/test-push` | Authenticated | Send test push to self |
| GET | `/notifications/fcm-status` | Authenticated | Check FCM configuration |

## Push Notification Infrastructure

### FCM Setup
- Firebase Admin SDK (lazy init, graceful degradation)
- Credentials via `FCM_CREDENTIALS_JSON` (raw JSON) or `FCM_CREDENTIALS_PATH` (file)
- Android: high priority; iOS: default sound + badge

### Token Management
- Stored on `User.fcm_token` (String 512, indexed)
- Registered via `PUT /api/v1/auth/me` with `fcm_token` field
- Single token per user (last login wins)

### Push Delivery Flow
```
_send_push_to_users(user_ids, title, body, action_url)
  -> Query users with fcm_token + push enabled
  -> Check NotificationPreference.enable_push per-user
  -> Check quiet_hours (overnight window supported)
  -> Filter to eligible tokens
  -> send_push_notification_to_users() with semaphore(10)
  -> Each: firebase_admin.messaging.send() via asyncio.to_thread
```

### Notification Send
```
POST /notifications/send {user_id?, target_roles?, send_push, send_email, ...}
  -> Create in-app notification(s)
  -> If send_push: _send_push_to_users()
  -> If send_email: enqueue ARQ send_notification_email_job
```

## Preferences

| Field | Type | Default | Effect |
|-------|------|---------|--------|
| `enable_push` | Boolean | True | Global push opt-out |
| `enable_email` | Boolean | True | Global email opt-out |
| `enable_sms` | Boolean | False | SMS channel |
| `quiet_hours_start` | String(5) | None | e.g. "22:00" |
| `quiet_hours_end` | String(5) | None | e.g. "07:00" |

**Enforcement:** `_send_push_to_users()` checks preferences server-side. Overnight quiet hours (e.g. 22:00-07:00) are supported.

## Push Events by Module

| Module | Event | Priority |
|--------|-------|----------|
| Rescue | Incident reported, dispatched, admitted, escalated | P0 |
| Adoption | Approved, completed, rejected | P0/P1 |
| Foster | Approved, dog placed/returned | P0/P1 |
| Lost & Found | Broadcast, sighting, match, contact release | P0 |
| Companion Pet | Safety tag scan, reminders (daily cron) | P0/P1 |
| Donation | Tax receipt, sponsorship created | P0/P1 |
| Auth | Password reset, MFA enabled/disabled | P1 |
| Grievance | SLA breached, escalation, assignment | P0/P1 |
| Fleet | Maintenance due, insurance expiry, equipment overdue | P0/P1 |
| Inventory | Low stock, item expiring | P0/P1 |

## Cross-Module Usage Pattern

```python
# Direct push (low latency):
from pawguard.modules.notifications.service import NotificationService
svc = NotificationService(repository=NotificationRepository(session))
await svc._send_push_to_users([user_id], title, body, action_url)

# Via NotificationSend (in-app + optional push + email):
from pawguard.modules.notifications.schemas import NotificationSend
await svc.send_notification(NotificationSend(
    user_id=user_id,
    title="...",
    body="...",
    notification_type="rescue_alert",
    action_url="/rescue/{id}",
    send_push=True,
    send_email=True,
))
```
