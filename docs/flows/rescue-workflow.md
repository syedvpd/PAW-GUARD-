# Rescue Workflow

## Overview

The rescue workflow is a state machine that tracks an animal emergency from initial report through verification, dispatch, and admission to shelter. The implementation is in `src/pawguard/modules/rescue/service.py`.

## State Machine

```
REPORTED --> VERIFIED --> DISPATCHED --> LOCATED --> RESCUED --> ADMITTED
    |                                           |
    +--> REJECTED (failed)                     +--> REJECTED (failed)
```

### Status Definitions

| Status | Description |
|--------|-------------|
| `reported` | Initial state after public or staff report |
| `verified` | Coordinator has verified the report |
| `dispatched` | Rescue team assigned and dispatched |
| `located` | Animal located by field team |
| `rescued` | Animal successfully rescued |
| `admitted` | Animal admitted to shelter, dog profile auto-created |
| `rejected` | Report rejected or rescue failed |

## Workflow Steps

### 1. Report Incident

**Actor**: Public user, rescue agent, or any authenticated user

**Endpoint**: `POST /rescue`

**Data Captured**:
- Reporter information (name, phone, email, anonymous option)
- Location (address, landmark, latitude, longitude)
- Animal count
- Physical condition (from `RescuePhysicalCondition` enum)
- Behavioral indicators
- Severity level (critical, high, medium, low)
- Urgent flag
- Media evidence (photos, videos)
- Environmental factors
- Reporter notes

**Side Effects**:
- Unique ticket number generated (`RES-YYYYMMDD-XXXX`)
- Audit event recorded (`rescue_reported`)
- Push notification to rescue coordinators
- Email confirmation to reporter (if not anonymous and has PawGuard account)
- Redis publish for real-time dispatch events

### 2. Verify Request

**Actor**: Rescue coordinator

**Endpoint**: `POST /rescue/{id}/verify`

**Validation**:
- Request must be in `REPORTED` status
- Rejection requires rationale
- Coordinator can refine severity and urgent flag

**Side Effects**:
- Audit event (`rescue_verified` or `rescue_rejected`)
- Redis publish for dispatch events

### 3. Dispatch Team

**Actor**: Rescue coordinator

**Endpoint**: `POST /rescue/{id}/dispatch`

**Data Captured**:
- Assigned driver
- Assigned agents (multi-agent support)
- Vehicle (must be ACTIVE status)
- Equipment details (auto-checkout from fleet)
- Escalation type (backup personnel, vet transport, law enforcement)
- Escalation notes

**Validation**:
- Request must be in `VERIFIED` status
- No existing dispatch record
- Vehicle must be ACTIVE
- All assigned users must exist

**Side Effects**:
- Dispatch record created
- Equipment auto-checked out from inventory
- Audit event (`rescue_dispatched`)
- Push notification to assigned agents
- Redis publish for real-time updates

### 4. Update Dispatch Status

**Actor**: Assigned rescue agent

**Endpoint**: `PATCH /rescue/{id}/dispatch/status`

**Valid Transitions**:
- `DISPATCHED` -> `LOCATED` (animal found)
- `DISPATCHED` or `LOCATED` -> `RESCUED` (animal secured)
- `RESCUED` -> `ADMITTED` (animal at shelter)
- `DISPATCHED` or `LOCATED` -> `REJECTED` (rescue failed)

**ADMITTED Side Effects**:
- Field report created
- Equipment released back to inventory
- Dog profile auto-created (`DogProfile` with status `RESCUED`)
- Audit event (`rescue_status_updated` with before/after state)
- Push notification to veterinarians
- Dashboard cache invalidated

**REJECTED Side Effects**:
- Failure reason recorded (from `RescueFailureReason` enum)
- Equipment released back to inventory

### 5. Add Observation Report

**Actor**: Assigned rescue agent

**Endpoint**: `POST /rescue/{id}/reports`

**Data Captured**:
- Agent ID
- Notes
- Photos (up to 5 URLs)

### 6. Escalate Case

**Actor**: Assigned rescue agent

**Endpoint**: `POST /rescue/{id}/escalate`

**Escalation Types**:
- `backup_personnel` - Request additional agents
- `vet_transport` - Need veterinary transport
- `law_enforcement` - Require law enforcement support
- `other` - Other escalation need

**Side Effects**:
- Audit event recorded
- Push notification to admins

### 7. Assign Coordinator

**Actor**: Admin or coordinator

**Endpoint**: `POST /rescue/{id}/assign-coordinator`

**Validation**:
- Coordinator user must exist and be active

### 8. Public Status Lookup

**Actor**: Reporter (unauthenticated)

**Endpoint**: `GET /rescue/status?ticket=...&phone=...`

**Security**:
- Ownership verified with ticket number AND phone number
- Guessing ticket number alone returns same error as invalid ticket
- No case data leaks through enumeration

## Bulk Operations

### Bulk Status Update

**Endpoint**: `POST /rescue/bulk/status`

**Valid Transitions**:
- `REPORTED` -> `VERIFIED`
- `VERIFIED` -> `DISPATCHED`
- `DISPATCHED` -> `LOCATED`
- `DISPATCHED` or `LOCATED` -> `RESCUED`
- `RESCUED` -> `ADMITTED`

**Note**: `REJECTED` is not bulk-applicable (requires per-request rationale/failure reason).

### Bulk Soft Delete

**Endpoint**: `POST /rescue/bulk/delete`

## Agent Location Tracking

**Endpoint**: `PATCH /rescue/agent/location`

**Data Captured**:
- Latitude, longitude
- Stored in Redis with 5-minute heartbeat TTL

**Nearby Agent Suggestion**:
- Redis geosearch within configurable radius
- Filters for active heartbeats
- Falls back to database listing if Redis empty

## Ticket Number Format

```
RES-YYYYMMDD-XXXX
```

- `YYYYMMDD`: Date of report
- `XXXX`: 4-digit random suffix
- Collision handling: retry up to 5 times with fresh suffix

## Physical Condition Categories

| Code | Description |
|------|-------------|
| `critical_life_threatening` | Critical / Life Threatening |
| `fractured_injured` | Fractured / Injured |
| `contagious_sick` | Contagious Disease / Sick |
| `malnourished` | Malnourished |
| `abandoned_stray` | Abandoned / Stray |
| `unknown` | Unknown (fallback) |

## Failure Reasons

| Code | Description |
|------|-------------|
| `animal_fled` | Animal Fled Area |
| `area_inaccessible` | Area Inaccessible |
| `false_report` | False Report |
| `local_intervention_blocked` | Local Intervention Blocked |
| `other` | Other (catch-all) |
