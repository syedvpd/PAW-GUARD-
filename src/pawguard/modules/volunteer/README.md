# Volunteer Module

Volunteer applications, shift management, attendance tracking, and service certificate generation.

---

## Architecture

```
volunteer/
  router.py          # 16 endpoints
  service.py         # VolunteerService (lifecycle, shifts, certificates)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## State Machine

```
APPLIED ──> ONBOARDED ──> ACTIVE ──> INACTIVE
   │                        │
   └──────────────────────> INACTIVE
```

**Activation gate:** `background_check_completed` must be True before transitioning to ACTIVE.

**Role granting:** `volunteer` role granted on ACTIVE (not at application time).

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `VolunteerProfile` | `volunteer_profiles` | Application: status, skills, background check |
| `VolunteerShift` | `volunteer_shifts` | Shift: role, time, capacity |
| `ShiftAttendance` | `shift_attendances` | Join/check-in/check-out + hours logged |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/volunteers/apply` | Auth (rate-limited) | Submit application |
| PUT | `/volunteers/{id}` | `volunteer:update` | Update / approve / activate |
| DELETE | `/volunteers/{id}` | `volunteer:update` | Soft delete |
| GET | `/volunteers` | `volunteer:update` | List profiles |
| GET | `/volunteers/{id}` | Owner or `volunteer:update` | Single profile |
| GET | `/volunteers/shifts` | `public:read` | List shifts |
| POST | `/volunteers/shifts` | `volunteer:schedule` | Create shift |
| POST | `/volunteers/shifts/{id}/join` | Authenticated | Join shift (row lock) |
| POST | `/volunteers/attendance/{id}/check-in` | Authenticated | Check in |
| POST | `/volunteers/attendance/{id}/check-out` | Authenticated | Check out |
| GET | `/volunteers/shifts/{id}/attendance` | `volunteer:read` | Shift attendance |
| GET | `/volunteers/{id}/certificate` | Owner or `volunteer:update` | Generate certificate PDF |
| GET | `/volunteers/{id}/service-summary` | Owner or `volunteer:update` | Service hours summary |
| POST | `/volunteers/bulk/delete` | `volunteer:update` | Bulk soft delete |
| POST | `/volunteers/bulk/status` | `volunteer:update` | Bulk status update |

## Key Flows

### Join Shift (with Row Lock)
```
POST /volunteers/shifts/{shift_id}/join
  -> Get volunteer profile (must exist, must be ACTIVE)
  -> SELECT ... FOR UPDATE on shift (serializes concurrent joins)
  -> Check duplicate (ConflictError if already joined)
  -> Check capacity (ConflictError if full)
  -> Create ShiftAttendance
```

### Check-In / Check-Out
```
Check-in:
  -> Set check_in_at = now

Check-out:
  -> Set check_out_at = now
  -> hours_logged = round((check_out - check_in).total_seconds() / 3600, 2)
```

### Certificate Generation
```
GET /volunteers/{id}/certificate
  -> Aggregate: total_hours, shifts_count, period, role_summary
  -> Generate PDF via reportlab (A4, org header, details table)
  -> Upload to storage: certificates/service_certificate_{id}.pdf
  -> Audit: VOLUNTEER_CERTIFICATE_ISSUED
```

## Background Check Requirement

- `background_check_completed`: staff-only field, NOT settable by applicant
- **Enforced at activation**: if False when transitioning to ACTIVE, raises ValidationFailedError
- `background_check_notes`: stores verification details

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| Activation | Auth | Grants `volunteer` role |
| Certificate request | Storage | PDF uploaded, presigned URL returned |
| Application | Notifications | In-app notification to coordinator |
