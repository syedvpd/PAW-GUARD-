# Grievance Module

Complaint tickets, service feedback, SLA tracking, escalation, and comment threads.

---

## Architecture

```
grievance/
  router.py          # 16 endpoints
  service.py         # GrievanceService (tickets, comments, escalation)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## State Machine

```
OPEN ──investigate──> INVESTIGATING ──await──> AWAITING_RESPONSE ──respond──> INVESTIGATING
 |                         |                         |
 └──close──> CLOSED        └──resolve──> RESOLVED    └──resolve──> RESOLVED
                                     RESOLVED ──close──> CLOSED
                                     CLOSED (terminal)
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `GrievanceTicket` | `grievance_tickets` | Complaint: subject, description, status, SLA, escalation |
| `GrievanceComment` | `grievance_comments` | Comment thread on tickets |
| `ServiceFeedback` | `service_feedback` | Separate feedback model |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/grievance` | Public (rate-limited) | Submit complaint |
| GET | `/grievance` | `grievance:read` | List tickets |
| GET | `/grievance/{id}` | `grievance:read` | Get ticket |
| PUT | `/grievance/{id}` | `grievance:update` | Update ticket |
| PATCH | `/grievance/{id}/status` | `grievance:update` | Update status |
| POST | `/grievance/{id}/assign` | `grievance:assign` | Assign admin |
| POST | `/grievance/{id}/escalate` | `grievance:assign` | Escalate ticket |
| POST | `/grievance/{id}/comments` | `grievance:comment` | Add comment |
| GET | `/grievance/{id}/comments` | `grievance:read` | List comments |
| POST | `/grievance/feedback` | Public (rate-limited) | Submit feedback |
| GET | `/grievance/feedback` | `grievance:read` | List feedback |
| DELETE | `/grievance/{id}` | `grievance:update` | Soft delete |
| POST | `/grievance/bulk/delete` | `grievance:update` | Bulk soft delete |
| POST | `/grievance/bulk/status` | `grievance:update` | Bulk status update |

## SLA Tracking

- **Default SLA:** 72 hours from submission (`DEFAULT_SLA_HOURS`)
- **Auto-escalation:** Background job `check_grievance_sla_escalation` runs periodically
  - Finds tickets where `sla_due_at < now` and `escalated_at IS NULL`
  - Increments `escalation_level`, sets `escalated_at = now`
  - Creates in-app notification + push to assigned admin

## Escalation Flow

```
POST /grievance/{id}/escalate {escalated_to_admin_id, reason}
  -> ticket.escalation_level += 1
  -> ticket.escalated_at = now
  -> ticket.escalated_to_admin_id = admin_id
  -> Create in-app notification to admin
  -> Push notification to admin
  -> Audit: GRIEVANCE_UPDATED
```

## Comment Thread

- `first_responded_at` set on first comment
- Comments are append-only (no edit/delete)
- Both assignee and complainant receive notifications

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| SLA breach (background job) | Notifications | Push + in-app to assigned admin |
| Escalation | Notifications | Push + in-app to escalated admin |
| Assignment | Notifications | Push to assigned admin |
| Ticket submitted | Notifications | In-app to admin queue |
