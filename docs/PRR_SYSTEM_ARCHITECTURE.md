# System Architecture, API Specs & DB Schema — Companion Pet Vertical (PRR)

This document covers the pet profiles & user-roles subsystem: system architecture,
API specifications, database schema, and the role model across **Owner**,
**Vet Clinic**, and **Admin**.

## 1. System Architecture

```
Client (Mobile App / Web / Admin Portal)
        │  HTTPS (RS256 JWT Bearer)
        ▼
┌───────────────────────────────────────────────┐
│  FastAPI v1 Router (auth → authorise →        │
│  validate → call service → return response)  │
└───────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│  Service layer (business behaviour, RBAC      │
│  scoping, audit, transaction boundaries)      │
└───────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│  Repository layer (data access only, no       │
│  business decisions)                          │
└───────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│  PostgreSQL (Supabase) — UUID PKs, FKs,       │
│  indexes, exclusion constraints, soft-delete  │
└───────────────────────────────────────────────┘

Background:  ARQ worker (Redis) → cron jobs + on-demand jobs
             (companion-pet reminders, lost-pet broadcast)
Cache:       Redis (RBAC permission lookup cache, rate limiting)
Storage:     S3 presigned uploads (medical history, rescue media)
Logging:     structlog + request ID + per-request latency metrics
```

**Architectural contracts enforced (AGENTS.md):**
- Routers never contain business logic and never touch the DB directly.
- Services own behaviour and permission scoping.
- Repositories execute queries only.
- No SQL in routers; no circular module coupling; domain ownership is respected
  (the companion_pet module never mutates `lost_found` state directly).

## 2. Role Model (Owner, Vet Clinic, Admin)

### 2.1 Roles & relevant permissions

| Role | Purpose | Companion-pet permissions |
|------|---------|----------------------------|
| `general_public` | Anonymous-friendly owner; emergency reporting | `companion_pet:{create,read,update,delete,medical_upload}`, `safety_tag:manage`, `vet_clinic:read`, `appointment:{create,read,cancel}`, `lost_found:broadcast` |
| `donor` | Donating owner | same as `general_public` + `dashboard:donor` |
| `rescue_agent` | Field rescue staff | `rescue:{create,read,execute}` |
| `rescue_centre_admin` / `shelter_admin` | Centre/shelter admin | admin bypass (unrestricted) |
| `super_admin` | System admin | admin bypass (unrestricted) |

**Vet Clinic staff** are authorisased through `ClinicMembership` rows
(`membership_role` e.g. `staff`, `vet`) on a `VetClinic`, not through a global
role. A membership grants `appointment:manage` (confirm/completed/no_show) scoped
to that clinic's appointments only. There is no separate "vet" global role; clinic
access is data-scoped, not role-wide.

### 2.2 Permission scoping rules (enforced in `CompanionPetService`)

```
Owner   → can only read/update/delete pets they own
Vet     → can read pets with an appointment at their clinic; cannot mutate the profile
Admin   → unrestricted (bypass via ADMIN_ROLES)
QR scan → public, PII-free, no auth; reveals only safe fields
```

## 3. API Specifications (v1)

Base path: `/api/v1`. All authenticated endpoints require
`Authorization: Bearer <access_token>`. Responses use the standard
`ApiResponse[T]` / `PaginatedResponse[T]` envelopes.

### 3.1 Pet Profiles

| Method | Path | Permission | Body | Returns |
|--------|------|------------|------|---------|
| POST | `/companion-pets` | `companion_pet:create` | `CompanionPetCreate` | `CompanionPetResponse` (201) |
| GET | `/companion-pets` | `companion_pet:read` | — | paginated (owner-scoped) |
| GET | `/companion-pets/{pet_id}` | `companion_pet:read` | — | `CompanionPetResponse` |
| PATCH | `/companion-pets/{pet_id}` | `companion_pet:update` | `CompanionPetUpdate` | `CompanionPetResponse` |
| DELETE | `/companion-pets/{pet_id}` | `companion_pet:delete` | — | 200 (soft delete) |

`CompanionPetCreate`: `name*`, `species` (def "dog"), `breed`, `sex`,
`birth_date`, `color`, `microchip_id`, `emergency_notes`, `is_scan_enabled` (def true).

`CompanionPetResponse`: id, owner_id, + create fields, `created_at`, `updated_at`.

### 3.2 Medical History Uploads

| Method | Path | Permission | Notes |
|--------|------|------------|-------|
| POST | `/companion-pets/{pet_id}/medical-files/upload-url` | `companion_pet:medical_upload` | presigned S3 URL |
| PUT | `/companion-pets/{pet_id}/medical-files/{file_id}/confirm` | `companion_pet:medical_upload` | confirm after S3 PUT |
| GET | `/companion-pets/{pet_id}/medical-files` | `companion_pet:read` | paginated |
| POST | `/companion-pets/{pet_id}/medical-records` | `companion_pet:medical_upload` | `MedicalRecordCreate` |
| GET | `/companion-pets/{pet_id}/medical-records` | `companion_pet:read` | list |
| DELETE | `/companion-pets/medical-records/{record_id}` | `companion_pet:medical_upload` | soft delete |

`MedicalRecordCreate`: `record_type*`, `title*`, `notes`, `occurred_at`,
`clinic_id`, `stored_file_id`.

### 3.3 QR Safety Tag Generation Engine

| Method | Path | Permission | Notes |
|--------|------|------------|-------|
| POST | `/companion-pets/{pet_id}/safety-tag` | `safety_tag:manage` | provision/rotate; returns `raw_token` ONCE |
| GET | `/companion-pets/{pet_id}/safety-tag` | `companion_pet:read` | metadata only (no token) |
| POST | `/companion-pets/safety-tag/scan` | public, rate-limited 20/min | PII-free public scan |

Engine guarantees: token is `secrets.token_urlsafe(48)`, only its **SHA-256 hash**
is persisted (`token_hash`, unique); the raw token is returned exactly once and
**never** readable again. Re-provisioning rotates and invalidates the prior
token. `token_prefix` is shown for identification only. See
`QR_SAFETY_TAGS.md` for the full engine design.

### 3.4 Vet Directory & Appointment Booking

| Method | Path | Permission | Notes |
|--------|------|------------|-------|
| GET | `/companion-pets/clinics` | public | paginated, searchable |
| POST | `/companion-pets/clinics` | `vet_clinic:manage` | create clinic |
| PATCH | `/companion-pets/clinics/{clinic_id}` | `vet_clinic:manage` | update |
| DELETE | `/companion-pets/clinics/{clinic_id}` | `vet_clinic:manage` | soft delete |
| POST | `/companion-pets/clinics/{clinic_id}/memberships` | `vet_clinic:manage` | authorise clinic staff |
| POST | `/companion-pets/appointments` | `appointment:create` | book (exclusion = no double-book) |
| GET | `/companion-pets/appointments` | `appointment:read` | filter `?pet_id=&clinic_id=` |
| GET | `/companion-pets/appointments/{appointment_id}` | `appointment:read` | detail |
| POST | `/companion-pets/appointments/{appointment_id}/confirm` | `appointment:manage` | clinic staff |
| POST | `/companion-pets/appointments/{appointment_id}/cancel` | `appointment:cancel` | owner/staff |

`PetAppointmentCreate`: `pet_id`, `clinic_id`, `vet_id?`, `starts_at`, `ends_at`
(end > start), `reason`, `notes?`. `AppointmentStatus` ∈
`requested, confirmed, cancelled, completed, no_show`.

### 3.5 Smart Reminders Engine

| Method | Path | Permission | Notes |
|--------|------|------------|-------|
| POST | `/companion-pets/{pet_id}/reminders` | `companion_pet:update` | `PetReminderCreate` |
| GET | `/companion-pets/{pet_id}/reminders` | `companion_pet:read` | list |
| DELETE | `/companion-pets/{pet_id}/reminders/{reminder_id}` | `companion_pet:update` | soft delete |

`PetReminderCreate`: `kind` (`vaccination`|`medication`), `title`, `details`,
`due_at`, `source_key` (idempotency key). Delivery runs via the ARQ cron
`send_companion_pet_reminders` (daily 09:45). See `SMART_REMINDERS_ENGINE.md`.

### 3.6 Lost Pet Alert System

| Method | Path | Permission | Notes |
|--------|------|------------|-------|
| POST | `/lost-found/lost` | authenticated | create lost report + GPS |
| GET | `/lost-found/lost` | public | list, reporter PII masked |
| POST | `/lost-found/lost/{report_id}/broadcast` | `lost_found:broadcast` | queues ARQ fan-out |
| POST | `/lost-found/found` | authenticated | create found report + GPS |
| GET | `/lost-found/lost/{report_id}/matches` | read | auto-matching by score |

See `LOST_PET_ALERT_SYSTEM.md` for broadcast/GPS/QR-scan flow.

## 4. Database Schema (migration `a0b1c2d3e4f5`)

All tables use UUID PKs, `created_at`/`updated_at` (TimestampMixin), and
soft-delete (`deleted_at`) where applicable.

```
companion_pets
  id            UUID PK
  owner_id      UUID FK -> users.id (CASCADE)
  name          VARCHAR(255) NOT NULL
  species       VARCHAR(64)  default 'dog'
  breed, sex, color, microchip_id, emergency_notes
  birth_date    TIMESTAMPTZ
  is_scan_enabled BOOLEAN default true
  deleted_at    TIMESTAMPTZ
  index: (owner_id, deleted_at)  unique: (microchip_id) where not null

pet_medical_records
  id            UUID PK
  pet_id        UUID FK -> companion_pets (CASCADE)
  clinic_id     UUID FK -> vet_clinics NULL
  authored_by_id UUID FK -> users
  stored_file_id UUID FK -> stored_files NULL
  record_type, title, notes, occurred_at
  index: (pet_id)

pet_safety_tags
  id            UUID PK
  pet_id        UUID FK -> companion_pets (CASCADE) one active tag per pet
  token_hash    VARCHAR(64) UNIQUE NOT NULL   -- SHA-256 of raw token
  token_prefix  VARCHAR(16)                   -- for identification only
  is_active     BOOLEAN
  last_scanned_at, scan_count
  unique: (pet_id) where is_active / unique: (token_hash)

vet_clinics
  id            UUID PK
  name, address, phone, email, services
  latitude, longitude
  is_emergency, is_active
  index: (is_active)

vet_clinic_memberships
  id            UUID PK
  clinic_id     UUID FK -> vet_clinics (CASCADE)
  user_id       UUID FK -> users (CASCADE)
  membership_role VARCHAR(32)   -- e.g. staff, vet
  unique: (clinic_id, user_id)

pet_appointments
  id            UUID PK
  pet_id        UUID FK -> companion_pets
  owner_id      UUID FK -> users
  clinic_id     UUID FK -> vet_clinics
  vet_id        UUID FK -> users NULL
  starts_at, ends_at, status, reason, notes, cancellation_reason
  EXCLUDE USING GIST (vet_id WITH =, tstzrange(starts_at, ends_at) WITH &&)
        WHERE vet_id IS NOT NULL AND status NOT IN (cancelled, completed, no_show)
  index: (clinic_id, starts_at), (pet_id, status)

pet_reminders
  id            UUID PK
  pet_id        UUID FK -> companion_pets (CASCADE)
  owner_id      UUID FK -> users
  kind          VARCHAR (vaccination|medication)
  title, details, due_at, source_key
  is_active     BOOLEAN
  unique: (pet_id, source_key)       -- idempotency
```

Migration `4f3c25a44f2e` adds `lost_reports.broadcasted_at` (index) for the
exactly-once broadcast marker.

## 5. Security & Audit

- Every mutating service call records an `AuthAuditEventType` entry with actor,
  IP, and structured metadata (before/after where relevant).
- RBAC lookups are Redis-cached (5 min TTL) and invalidated on role changes.
- Rate limits: safety-tag scan 20/min, public rescue report 5/min, broadcast 3/h.
- Privacy: public scan exposes no owner PII; public lost/found listing masks
  reporter email/name/phone.

## 6. Clients

The same `/api/v1` surface serves all four supported clients (Mobile App, Admin
Portal, Rescue Staff App, Executive App). Role differentiation is by JWT role
and clinic membership, not by separate endpoints.