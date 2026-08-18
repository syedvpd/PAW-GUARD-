# Rescue Module

Emergency animal rescue lifecycle management — from public incident reporting through field dispatch to shelter admission.

---

## Architecture

```
rescue/
  router.py          # 25 endpoints (authenticated + public routers)
  admin_router.py    # Admin aliases
  service.py         # RescueService (state machine, dispatch, agent tracking)
  repository.py      # Data access (requests, dispatches, reports)
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
  exceptions.py      # Rescue-specific errors
```

## State Machine

```
REPORTED ──approve──> VERIFIED ──dispatch──> DISPATCHED ──locate──> LOCATED ──secure──> RESCUED ──admit──> ADMITTED
    │                     │                      │                    │
    │ reject              │                      │ fail               │ fail
    v                     v                      v                    v
  REJECTED             REJECTED               REJECTED             REJECTED
```

| From | To | Endpoint | Permission |
|------|----|----------|------------|
| REPORTED | VERIFIED | `POST /{id}/verify` (approve=true) | `rescue:verify` |
| REPORTED | REJECTED | `POST /{id}/verify` (approve=false + rationale) | `rescue:verify` |
| VERIFIED | DISPATCHED | `POST /{id}/dispatch` | `rescue:dispatch` |
| DISPATCHED | LOCATED | `POST /{id}/located` | `rescue:execute` |
| DISPATCHED/LOCATED | RESCUED | `POST /{id}/secured` | `rescue:execute` |
| RESCUED | ADMITTED | `POST /{id}/admitted` | `rescue:dispatch` |
| Any | REJECTED | `POST /{id}/fail` (failure_reason) | `rescue:execute` |

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `RescueRequest` | `rescue_requests` | Core case: reporter info, location, status, severity, coordinator |
| `RescueDispatch` | `rescue_dispatches` | 1:1 with request. Driver, vehicle, equipment, timestamps |
| `RescueDispatchAgent` | `rescue_dispatch_agents` | M:N dispatch-agent association |
| `RescueReport` | `rescue_reports` | Agent observation reports (photos, notes). Append-only |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/rescue/report` | `rescue:create` | Staff incident report (rate-limited 5/min) |
| POST | `/public/rescue/report` | Public | Anonymous emergency intake (rate-limited 5/min) |
| POST | `/rescue/media-upload-url` | Authenticated | Presigned S3 upload URL (50MB max) |
| POST | `/rescue/{id}/verify` | `rescue:verify` | Approve/reject report, refine severity |
| POST | `/rescue/{id}/assign-coordinator` | `rescue:dispatch` | Assign coordinator |
| POST | `/rescue/{id}/dispatch` | `rescue:dispatch` | Create dispatch, assign team + vehicle |
| PATCH | `/rescue/dispatches/{id}` | `rescue:dispatch` | Update dispatch details |
| POST | `/rescue/{id}/escalate` | `rescue:update` | Escalate case |
| POST | `/rescue/{id}/located` | `rescue:execute` | Mark animal located |
| POST | `/rescue/{id}/secured` | `rescue:execute` | Mark animal rescued |
| POST | `/rescue/{id}/admitted` | `rescue:dispatch` | Admit to shelter (auto-creates DogProfile) |
| POST | `/rescue/{id}/fail` | `rescue:execute` | Mark rescue failed |
| POST | `/rescue/{id}/accept` | `rescue:execute` | Agent acknowledges dispatch |
| POST | `/rescue/{id}/reports` | `rescue:execute` | Add observation report |
| GET | `/rescue/status` | Public | Ticket + phone lookup |
| GET | `/rescue/dispatches` | `rescue:read` | Paginated dispatch list |
| GET | `/rescue/{id}` | Optional auth | Single rescue request |
| GET | `/rescue` | Optional auth | Paginated list with filters |
| DELETE | `/rescue/{id}` | `rescue:execute` | Soft delete |
| POST | `/rescue/bulk/status-update` | `rescue:execute` | Bulk status (state machine enforced) |
| POST | `/rescue/bulk/delete` | `rescue:execute` | Bulk soft delete |
| POST | `/rescue/agents/location` | `rescue:execute` | GPS heartbeat (Redis GEO, 5min TTL) |
| GET | `/rescue/{id}/suggest-agents` | `rescue:dispatch` | Nearest active agents |

## Business Rules

### Ticket Generation
- Format: `RES-YYYYMMDD-XXXX` (4 random digits)
- Retry loop (5 attempts) on collision
- Concurrent claim protected by IntegrityError rollback

### Agent Assignment Enforcement
- Rescue agents can ONLY act on cases they are assigned to
- Enforcement checks both `assigned_driver_id` and `RescueDispatchAgent` table
- Coordinators and admins bypass this restriction

### Reporter PII Masking
- ALL responses mask: name, phone, email
- Unmasked only for: `rescue:verify`, `rescue:dispatch`, `system:admin`

### Public Status Lookup
- Requires BOTH ticket number AND phone number
- Returns minimal data (no PII)

## Cross-Module Interactions

| Trigger | Target Module | Effect |
|---------|---------------|--------|
| ADMITTED status | Dog | Auto-creates `DogProfile` (status=RESCUED, is_adoptable=False) |
| DISPATCH created | Fleet | Auto-checkout equipment via `checkout_equipment_for_dispatch()` |
| ADMITTED/REJECTED | Fleet | Release all checked-out equipment |
| Various events | Notifications | Push to coordinators, agents, vets, admins |
| Every action | Auth Audit | Structured audit event with before/after state |
