# PawGuard — Push Notification Audit (Firebase Cloud Messaging)

**Date:** 2026-08-18
**Status:** Infrastructure ready, domain integration incomplete

---

## Executive Summary

Firebase Cloud Messaging is **configured and functional** at the infrastructure level.
The `push_service.py` layer sends real FCM messages. The `NotificationService` has a
`_send_push_to_users()` bridge method. Device tokens are stored on the `User` model.

**Current state:** Only **1 out of ~40+ business workflows** actually triggers push
notifications (companion pet reminders). Every other module creates in-app
notifications and/or sends email, but never sets `send_push=True`.

---

## 1. Push Infrastructure (What Exists)

### 1.1 Core FCM Integration

| Component | File | Status |
|-----------|------|--------|
| FCM send (single device) | `services/push_service.py:50-95` | Working |
| FCM send (fan-out batch) | `services/push_service.py:98-131` | Working |
| Firebase lazy init | `services/push_service.py:14-47` | Working (graceful degrade) |
| FCM credentials config | `core/config.py:147-151` | `fcm_credentials_path` / `fcm_credentials_json` |

### 1.2 Device Token Management

| Component | File | Status |
|-----------|------|--------|
| `User.fcm_token` column | `modules/auth/models.py:234` | Exists (String 512, indexed) |
| `User.push_notifications_enabled` | `modules/auth/models.py:233` | Exists (bool, default True) |
| Token registration endpoint | `PUT /api/v1/auth/me` via `auth/router.py:323-349` | Working |
| Token stored on profile update | `auth/service.py:880-915` | Working |

### 1.3 Notification Service Bridge

| Component | File | Status |
|-----------|------|--------|
| `_send_push_to_users()` | `modules/notifications/service.py:247-281` | Working |
| `send_notification()` with `send_push` flag | `modules/notifications/service.py:165-245` | Working |
| `NotificationSend.send_push` field | `modules/notifications/schemas.py:81` | Exists (default `False`) |

### 1.4 Preference Model (Partially Wired)

| Component | File | Status |
|-----------|------|--------|
| `NotificationPreference.enable_push` | `modules/notifications/models.py:44` | Exists, **NOT checked** by push delivery |
| `NotificationPreference.quiet_hours_*` | `modules/notifications/models.py:47-48` | Exists, **NOT checked** by push delivery |
| Preference API endpoints | `modules/notifications/router.py:175-219` | Working |

---

## 2. Where Push Notifications ARE Sent (Current)

| # | Module | Trigger | File:Line | Mechanism |
|---|--------|---------|-----------|-----------|
| 1 | Companion Pet | Vaccination/medication reminder due (daily cron 09:45) | `companion_pet/service.py:1020-1026` | Direct `_send_push_to_users()` call |
| 2 | Notifications (manual) | Admin sends notification via API with `send_push=True` | `notifications/router.py:142-173` | `NotificationService.send_notification()` |

**That is all.** No other module sends push notifications.

---

## 3. Where Push Notifications SHOULD Be Sent (Gap Analysis)

### 3.1 Auth Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Password reset requested | Email only | **Yes** | P1 | Security alert — user should know immediately |
| MFA enabled/disabled | Audit only | **Yes** | P1 | Security-critical account change |
| New login from unknown device | Nothing | **Yes** | P0 | Security: immediate alert |
| Account locked (5 failed logins) | Audit only | **Yes** | P1 | User needs to know they're locked out |
| Session revoked | Nothing | **Yes** | P2 | Awareness of forced logout |
| Profile updated | Audit only | No | — | Low value push |
| OAuth linked/unlinked | Audit only | **Yes** | P2 | Security awareness |

### 3.2 Rescue Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Incident reported | Email to reporter | **Yes** to coordinator | P0 | Coordinators need immediate awareness of new cases |
| Report verified | Nothing | **Yes** to reporter | P1 | Reporter should know their report was verified |
| Team dispatched | Email only | **Yes** to assigned agent | P0 | Agent needs immediate notification to mobilize |
| Agent located animal | Nothing | **Yes** to coordinator | P1 | Coordination update |
| Animal rescued (in transit) | Nothing | **Yes** to coordinator + shelter | P1 | Shelter should prepare for intake |
| Animal admitted | Nothing | **Yes** to coordinator + vet | P0 | Vet needs to schedule intake exam |
| Rescue failed | Nothing | **Yes** to coordinator | P1 | Awareness of failed attempt |
| Escalation | Nothing | **Yes** to admin + coordinator | P0 | Urgent escalation needs immediate attention |
| New rescue report (public) | Nothing to staff | **Yes** to all rescue agents | P0 | Field agents need to know about new cases in their area |

### 3.3 Adoption Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Application submitted | In-app + email | **Yes** to adopter | P1 | Confirmation of submission |
| Application screening started | Nothing | **Yes** to adopter | P2 | Status update |
| Interview scheduled | Nothing | **Yes** to adopter | P0 | Time-sensitive — adopter needs to prepare |
| Home check scheduled | Nothing | **Yes** to adopter | P0 | Time-sensitive — adopter needs to be home |
| Application approved | In-app + email | **Yes** to adopter | P0 | Major milestone — adopter excited |
| Application rejected | In-app + email | **Yes** to adopter | P1 | Important to know promptly |
| Adoption completed | In-app + email | **Yes** to adopter | P0 | Celebration + next steps |
| Follow-up reminder (30/90/180 day) | In-app + email | **Yes** to adopter | P1 | Time-sensitive task |
| Dog becomes adoptable (medical clearance) | Nothing | **Yes** to adoption coordinators | P1 | New dog available for matching |

### 3.4 Foster Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Application submitted | Nothing | **Yes** to foster coordinator | P1 | New application needs review |
| Application approved | Nothing | **Yes** to foster family | P0 | Major milestone — they can now foster |
| Application rejected | Nothing | **Yes** to foster family | P1 | Important to know promptly |
| Dog placed in foster care | Nothing | **Yes** to foster family | P0 | They need to prepare for the dog |
| Dog returned from foster | Nothing | **Yes** to foster family + shelter | P1 | Coordination for return logistics |
| Daily progress log due | Nothing | **Yes** to foster family | P2 | Reminder to log progress |
| Foster-to-adoption conversion | Nothing | **Yes** to foster family | P0 | Major milestone |
| Supply dispatch | Nothing | **Yes** to foster family | P2 | Supplies arriving |

### 3.5 Volunteer Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Application submitted | In-app + email | **Yes** to volunteer coordinator | P1 | New application needs review |
| Application approved | In-app + email | **Yes** to volunteer | P0 | They're onboarded |
| Shift created | Nothing | **Yes** to available volunteers | P1 | New shift opportunity |
| Shift reminder (day before) | Nothing | **Yes** to signed-up volunteers | P0 | Prevent no-shows |
| Check-in reminder | Nothing | **Yes** to volunteers at location | P2 | Prompt check-in |
| Service certificate issued | Nothing | **Yes** to volunteer | P1 | Recognition |

### 3.6 Fleet Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Vehicle maintenance due | In-app only | **Yes** to fleet manager | P1 | Preventive maintenance |
| Insurance expiring (30 days) | In-app only | **Yes** to fleet manager | P1 | Compliance deadline |
| Equipment overdue (not returned) | In-app only | **Yes** to assigned agent + fleet manager | P0 | Urgent — equipment missing |
| Vehicle assigned to dispatch | Nothing | **Yes** to assigned driver | P0 | Driver needs to mobilize |
| Vehicle status changed | Nothing | **Yes** to fleet manager | P2 | Fleet awareness |

### 3.7 Inventory Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Low stock alert | In-app only | **Yes** to inventory manager + rescue centre admin | P1 | Prevent stockout |
| Item expiring soon (60 days) | In-app only | **Yes** to inventory manager | P1 | Waste prevention |
| Requisition approved | Nothing | **Yes** to requesting user | P1 | Their request was fulfilled |
| Requisition rejected | Nothing | **Yes** to requesting user | P1 | Need to know to re-request or escalate |
| Stock critically low | In-app only | **Yes** to rescue centre admin | P0 | Operational impact |

### 3.8 Shelter Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Transfer requested | Nothing | **Yes** to receiving shelter manager | P0 | Time-sensitive coordination |
| Transfer confirmed (both sides) | Nothing | **Yes** to both parties + coordinator | P1 | Transfer complete |
| Kennel needs cleaning | Nothing | **Yes** to shelter staff | P2 | Hygiene maintenance |
| Dog assigned to kennel | Nothing | **Yes** to shelter manager | P2 | Awareness |
| Daily care log submitted | Nothing | No | — | Low value |
| Facility capacity reached | Nothing | **Yes** to shelter manager + coordinator | P1 | Overflow planning |

### 3.9 Donation Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Donation received | In-app + email | **Yes** to donor | P1 | Gratitude + confirmation |
| Tax receipt generated | In-app + email | **Yes** to donor | P0 | Tax document — high value |
| Sponsorship created | In-app + email | **Yes** to donor | P1 | Confirmation |
| Sponsorship charge processed | In-app + email | **Yes** to donor | P1 | Financial awareness |
| Campaign goal reached | Nothing | **Yes** to campaign creator + donors | P0 | Celebration + impact |
| Recurring donation failed | Nothing | **Yes** to donor | P0 | Payment issue — needs action |
| Sponsorship paused/cancelled | Nothing | **Yes** to donor + shelter | P1 | Awareness |

### 3.10 Finance Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Transaction posted | Nothing | **Yes** to finance_user | P2 | Awareness |
| Reconciliation completed | Nothing | **Yes** to finance_user + admin | P1 | Audit trail awareness |
| Budget exceeded | Nothing | **Yes** to finance_user + admin | P0 | Financial control |
| Anomalous transaction flagged | Nothing | **Yes** to finance_user + admin | P0 | Fraud prevention |

### 3.11 Lost & Found Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Lost pet broadcast | In-app to all users (no push) | **Yes** to all users | P0 | **CRITICAL** — community needs to be alert |
| Potential match found | Email to both parties | **Yes** to both parties | P0 | High urgency — may reunite pet |
| Sighting reported | Email to owner | **Yes** to owner | P0 | Someone saw their pet |
| Match confirmed (contact release) | Email both parties | **Yes** to both parties | P0 | Reunion coordination |
| Ownership claim submitted | Nothing | **Yes** to reporter + claimant | P1 | Status update |
| Ownership claim reviewed | Nothing | **Yes** to claimant | P0 | Resolution |
| Report expired | Nothing | **Yes** to reporter | P2 | Awareness |

### 3.12 Companion Pet Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Vaccination/medication reminder due | **YES (working)** | Already working | — | Only module with working push |
| Appointment requested | Nothing | **Yes** to clinic | P1 | New booking |
| Appointment confirmed | Nothing | **Yes** to pet owner | P0 | Time-sensitive |
| Appointment reminder (24h) | Nothing | **Yes** to pet owner | P0 | Prevent no-show |
| Appointment cancelled | Nothing | **Yes** to pet owner + clinic | P1 | Awareness |
| Safety tag scanned | Nothing | **Yes** to pet owner | P0 | **CRITICAL** — someone found their pet |
| Medical record added | Nothing | **Yes** to pet owner | P1 | Health awareness |

### 3.13 Grievance Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| Complaint submitted | Nothing | **Yes** to admin | P1 | New grievance needs attention |
| Ticket assigned | Nothing | **Yes** to assigned admin | P0 | They need to act |
| SLA approaching (48h) | Nothing | **Yes** to assigned admin | P0 | Prevent SLA breach |
| SLA breached | Nothing | **Yes** to admin + escalation target | P0 | Escalation trigger |
| Ticket resolved | Nothing | **Yes** to complainant | P1 | Resolution notification |
| Comment added | Nothing | **Yes** to ticket assignee + complainant | P2 | Conversation update |

### 3.14 Portal / CMS Module

| Business Event | Currently Sends | Should Push? | Priority | Notes |
|----------------|----------------|--------------|----------|-------|
| New CMS page published | Nothing | **Yes** to all users | P2 | Content update (optional) |
| Emergency alert published | Nothing | **Yes** to all users | P0 | Critical system-wide alert |

---

## 4. Background Workers — Push Notification Gaps

| Worker | File | Currently Sends Push? | Should Add Push? |
|--------|------|----------------------|------------------|
| `broadcast_lost_pet_alert` | `workers/jobs/lost_found_jobs.py:18-57` | No (in-app only) | **Yes — P0** |
| `check_inventory_low_stock` | `workers/jobs/scheduled_jobs.py:106` | No (in-app only) | Yes — P1 |
| `check_inventory_expiry` | `workers/jobs/scheduled_jobs.py:148` | No (in-app only) | Yes — P1 |
| `check_vaccination_renewals` | `workers/jobs/scheduled_jobs.py` | No (in-app only) | Yes — P1 |
| `post_adoption_followups` | `workers/jobs/scheduled_jobs.py:220` | No (in-app + email) | Yes — P1 |
| `process_sponsorship_charges` | `workers/jobs/scheduled_jobs.py:332` | No (in-app + email) | Yes — P1 |
| `send_companion_pet_reminders` | `workers/jobs/companion_pet_jobs.py:13` | **YES (working)** | Already working |
| `check_grievance_sla_escalation` | (grievance worker) | No | Yes — P0 |
| Fleet maintenance check | `workers/jobs/fleet_jobs.py:47` | No (in-app only) | Yes — P1 |
| Fleet insurance expiry | `workers/jobs/fleet_jobs.py:87` | No (in-app only) | Yes — P1 |
| Overdue equipment | `workers/jobs/fleet_jobs.py:140` | No (in-app only) | Yes — P0 |

---

## 5. Notification Preference Gaps

### 5.1 Preferences NOT checked during push delivery

The `NotificationPreference` model stores `enable_push`, `quiet_hours_start`, and
`quiet_hours_end`, but `_send_push_to_users()` only checks the user-level
`User.push_notifications_enabled` flag. The per-user preferences are ignored.

**Fix needed in:** `modules/notifications/service.py:247-281`

```python
# Current filter (line 263-269):
#   User.push_notifications_enabled == True
#   User.fcm_token IS NOT NULL
#   User.fcm_token != ''

# Should ALSO check:
#   NotificationPreference.enable_push == True  (if preference exists)
#   NOT within quiet hours window
```

### 5.2 No per-notification-type push preferences

Users cannot currently opt out of specific notification types (e.g., "send me push
for rescue alerts but not for donation updates"). The `enable_push` flag is global.

**Future consideration:** Add a `notification_type` dimension to preferences.

---

## 6. Implementation Checklist

### Phase 0 — Infrastructure Fixes (Do First)

- [ ] Wire `NotificationPreference.enable_push` into `_send_push_to_users()` filter
- [ ] Wire `NotificationPreference.quiet_hours_*` into `_send_push_to_users()` filter
- [ ] Add `firebase_admin` to `pyproject.toml` dependencies (currently lazy/optional)
- [ ] Ensure `FCM_CREDENTIALS_PATH` is set in production environment

### Phase 1 — Critical Push (P0)

| # | Module | Event | Implementation |
|---|--------|-------|----------------|
| 1 | Lost & Found | Lost pet broadcast | Add `send_push=True` to `broadcast_lost_pet_alert` job |
| 2 | Lost & Found | Safety tag scanned | Add `_send_push_to_users()` call in `scan_safety_tag()` |
| 3 | Rescue | New incident reported | Add `_send_push_to_users()` to coordinator(s) in `report_incident()` |
| 4 | Rescue | Team dispatched | Add `_send_push_to_users()` to agent in `dispatch_team()` |
| 5 | Rescue | Animal admitted | Add `_send_push_to_users()` to vet in `update_dispatch_status()` |
| 6 | Rescue | Escalation | Add `_send_push_to_users()` to admin in `escalate()` |
| 7 | Adoption | Application approved | Set `send_push=True` in `_notify_adopter()` |
| 8 | Adoption | Adoption completed | Set `send_push=True` in `_notify_adopter()` |
| 9 | Foster | Application approved | Add `_send_push_to_users()` to foster family |
| 10 | Foster | Dog placed | Add `_send_push_to_users()` to foster family |
| 11 | Donation | Tax receipt ready | Set `send_push=True` in receipt notification |
| 12 | Donation | Campaign goal reached | Add broadcast with push to campaign donors |
| 13 | Companion Pet | Safety tag scanned | Add `_send_push_to_users()` to owner (already has infrastructure) |
| 14 | Auth | New login (unknown device) | Add `_send_push_to_users()` security alert |
| 15 | Grievance | SLA breached | Add `_send_push_to_users()` to admin |

### Phase 2 — Important Push (P1)

| # | Module | Event | Implementation |
|---|--------|-------|----------------|
| 16 | Rescue | Report verified | Push to reporter |
| 17 | Rescue | Agent located animal | Push to coordinator |
| 18 | Rescue | Animal rescued (transit) | Push to coordinator + shelter |
| 19 | Adoption | Interview scheduled | Push to adopter |
| 20 | Adoption | Home check scheduled | Push to adopter |
| 21 | Adoption | Application rejected | Push to adopter |
| 22 | Adoption | Follow-up reminder | Push to adopter |
| 23 | Foster | Application rejected | Push to foster family |
| 24 | Foster | Dog returned | Push to foster family + shelter |
| 25 | Volunteer | Application approved | Push to volunteer |
| 26 | Volunteer | Shift created | Push to available volunteers |
| 27 | Volunteer | Shift reminder | Push to signed-up volunteers |
| 28 | Fleet | Equipment overdue | Push to assigned agent + fleet manager |
| 29 | Fleet | Insurance expiring | Push to fleet manager |
| 30 | Inventory | Low stock | Push to inventory manager |
| 31 | Inventory | Requisition approved/rejected | Push to requesting user |
| 32 | Shelter | Transfer requested | Push to receiving shelter manager |
| 33 | Donation | Donation received | Push to donor |
| 34 | Donation | Sponsorship charge processed | Push to donor |
| 35 | Donation | Recurring donation failed | Push to donor |
| 36 | Lost & Found | Potential match found | Push to both parties |
| 37 | Lost & Found | Sighting reported | Push to owner |
| 38 | Companion Pet | Appointment confirmed | Push to pet owner |
| 39 | Companion Pet | Appointment reminder | Push to pet owner |
| 40 | Grievance | Ticket assigned | Push to assigned admin |
| 41 | Grievance | Complaint submitted | Push to admin |
| 42 | Auth | Password reset requested | Push to user (security) |
| 43 | Auth | MFA enabled/disabled | Push to user (security) |

### Phase 3 — Nice-to-Have Push (P2)

| # | Module | Event | Implementation |
|---|--------|-------|----------------|
| 44 | Auth | Session revoked | Push to user |
| 45 | Auth | OAuth linked/unlinked | Push to user |
| 46 | Foster | Daily progress log due | Push to foster family |
| 47 | Foster | Supply dispatch | Push to foster family |
| 48 | Volunteer | Certificate issued | Push to volunteer |
| 49 | Volunteer | Check-in reminder | Push to volunteers |
| 50 | Fleet | Vehicle status changed | Push to fleet manager |
| 51 | Shelter | Kennel needs cleaning | Push to shelter staff |
| 52 | Shelter | Dog assigned to kennel | Push to shelter manager |
| 53 | Finance | Budget exceeded | Push to finance_user + admin |
| 54 | Finance | Anomalous transaction | Push to finance_user + admin |
| 55 | Lost & Found | Report expired | Push to reporter |
| 56 | Companion Pet | Medical record added | Push to pet owner |
| 57 | CMS | Emergency alert published | Push to all users |
| 58 | Adoption | Dog becomes adoptable | Push to adoption coordinators |

---

## 7. Architecture Notes

### 7.1 Push Delivery Pattern

All domain services should follow the same pattern used by `companion_pet/service.py`:

```python
from pawguard.modules.notifications.service import NotificationService

# Inside the service method, after the business event:
await notification_service.send_notification(
    NotificationSend(
        user_id=target_user_id,
        title="Event Title",
        body="Event description",
        notification_type="rescue_alert",  # typed category
        action_url=f"/api/v1/rescue/{rescue_id}",  # deep-link
        send_push=True,    # <-- THIS IS THE KEY FLAG
        send_email=False,  # or True as needed
    )
)
```

### 7.2 Direct Push (Bypassing NotificationSend)

For urgent real-time alerts (e.g., rescue dispatch, safety tag scan), use
`_send_push_to_users()` directly for lower latency:

```python
from pawguard.modules.notifications.service import get_notification_service

notification_service = get_notification_service()
await notification_service._send_push_to_users(
    user_ids=[target_user_id],
    title="Urgent: New Rescue Case",
    body="A new emergency has been reported nearby.",
    action_url=f"/api/v1/rescue/{rescue_id}",
)
```

### 7.3 Broadcast Push (Multiple Users)

For broadcasts (lost pet alerts, emergency alerts), use the batch method:

```python
# Get all active user IDs with FCM tokens
# Then call:
await notification_service._send_push_to_users(
    user_ids=all_user_ids,
    title="Lost Pet Alert",
    body="A pet has been reported lost in your area.",
    action_url="/api/v1/lost-found",
)
```

### 7.4 Single Token Push (Direct Device)

For device-to-device or tag-based scenarios:

```python
from pawguard.services.push_service import send_push_notification

await send_push_notification(
    fcm_token=target_token,
    title="Your pet was found!",
    body="Someone scanned your pet's safety tag.",
    data={"pet_id": str(pet_id), "type": "safety_tag_scan"},
)
```

---

## 8. Current Push Notification Flow Diagram

```
Flutter App
  │
  ├─ Login / Token Refresh
  │   └─ PUT /api/v1/auth/me { fcm_token: "..." }
  │       └─ Stored in users.fcm_token
  │
  ├─ User triggers action (e.g., sends notification via admin)
  │   └─ POST /api/v1/notifications/send { send_push: true }
  │       └─ NotificationService.send_notification()
  │           └─ _send_push_to_users()
  │               └─ Queries users with fcm_token + push_enabled
  │                   └─ send_push_notification_to_users()
  │                       └─ send_push_notification() [per device]
  │                           └─ firebase_admin.messaging.send()
  │
  └─ Companion Pet Reminder (daily cron)
      └─ send_companion_pet_reminders
          └─ deliver_reminder_once()
              └─ _send_push_to_users()
                  └─ (same FCM flow as above)
```

---

## 9. Files Reference

| File | Purpose |
|------|---------|
| `src/pawguard/services/push_service.py` | Core FCM integration |
| `src/pawguard/modules/notifications/service.py` | Notification orchestration + `_send_push_to_users()` |
| `src/pawguard/modules/notifications/models.py` | Notification + NotificationPreference models |
| `src/pawguard/modules/notifications/schemas.py` | `NotificationSend.send_push` flag |
| `src/pawguard/modules/notifications/router.py` | Notification API endpoints |
| `src/pawguard/modules/auth/models.py:233-234` | `User.fcm_token` + `push_notifications_enabled` |
| `src/pawguard/modules/auth/service.py:880-915` | FCM token storage on profile update |
| `src/pawguard/core/config.py:147-151` | FCM credential configuration |
| `src/pawguard/modules/companion_pet/service.py:1020-1026` | Only working push trigger |
| `src/pawguard/workers/jobs/lost_found_jobs.py` | Lost pet broadcast (needs push) |
| `src/pawguard/workers/jobs/scheduled_jobs.py` | Scheduled workers (most need push) |
| `src/pawguard/workers/jobs/fleet_jobs.py` | Fleet alert workers (need push) |
| `src/pawguard/workers/arq_worker.py` | Worker registration + cron schedules |
