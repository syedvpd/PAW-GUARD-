# Companion Pet Module

Personal pet registration, medical records, safety tags (QR), vet clinics, appointments, and vaccination/medication reminders.

---

## Architecture

```
companion_pet/
  router.py          # 28+ endpoints
  service.py         # CompanionPetService (pets, tags, clinics, appointments)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `CompanionPet` | `companion_pets` | Personal pet record |
| `PetMedicalRecord` | `pet_medical_records` | Vaccination/medication records |
| `SafetyTag` | `safety_tags` | QR code tag (hashed token, scan tracking) |
| `PetReminder` | `pet_reminders` | Vaccination/medication reminders |
| `ReminderDelivery` | `reminder_deliveries` | Delivery audit (dedup guard) |
| `VetClinic` | `vet_clinics` | Veterinary clinic directory |
| `ClinicMembership` | `clinic_memberships` | Vet-clinic association |
| `PetClinicAccess` | `pet_clinic_access` | Pet-clinic booking access |
| `PetAppointment` | `pet_appointments` | Appointment bookings |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/companion-pets` | `companion_pet:create` | Register pet |
| GET | `/companion-pets` | `companion_pet:read` | List my pets |
| GET | `/companion-pets/{id}` | `companion_pet:read` | Get pet |
| PATCH | `/companion-pets/{id}` | `companion_pet:update` | Update pet |
| DELETE | `/companion-pets/{id}` | `companion_pet:delete` | Delete pet |
| POST | `/companion-pets/{id}/medical-records` | `companion_pet:medical_upload` | Add medical record |
| GET | `/companion-pets/{id}/medical-records` | `companion_pet:read` | List medical records |
| POST | `/companion-pets/{id}/safety-tag` | `safety_tag:manage` | Provision QR tag |
| GET | `/companion-pets/{id}/safety-tag` | `companion_pet:read` | Get tag info |
| DELETE | `/companion-pets/{id}/safety-tag` | `safety_tag:manage` | Deactivate tag |
| POST | `/companion-pets/safety-tag/scan` | Public (rate-limited) | Scan QR tag |
| POST | `/companion-pets/{id}/reminders` | `companion_pet:update` | Create reminder |
| GET | `/companion-pets/{id}/reminders` | `companion_pet:read` | List reminders |
| POST | `/companion-pets/appointments` | `appointment:create` | Book appointment |
| POST | `/companion-pets/appointments/{id}/confirm` | `appointment:manage` | Confirm appointment |
| POST | `/companion-pets/clinics` | `vet_clinic:manage` | Create clinic |
| GET | `/companion-pets/clinics` | Public | List clinics |
| POST | `/companion-pets/from-adoption/{app_id}` | `companion_pet:create` | Pet from adoption |

## Safety Tag Scan Flow

```
POST /companion-pets/safety-tag/scan {token}
  -> Hash token (SHA-256), lookup SafetyTag
  -> Update scan_count, last_scanned_at
  -> If pet has active lost report: return lost status + location
  -> Return: name, breed, color, owner info (PII masked), facility info
  -> Push notification to pet owner: "Your pet's safety tag was scanned!"
```

## Reminder System

**Auto-creation:** When a medical record is created with `next_reminder_at`, a `PetReminder` is auto-created.

**Delivery:** Background job `send_companion_pet_reminders` runs daily at 09:45:
1. Find reminders due within 24 hours
2. Create `ReminderDelivery` (dedup guard — unique constraint)
3. Create in-app notification
4. **Send push notification via FCM** (only module with working push)

## Appointment Lifecycle

```
REQUESTED ──confirm──> CONFIRMED ──complete──> COMPLETED
    │                      │
    └──cancel──> CANCELLED └──no_show──> NO_SHOW
```

## Pet from Adoption

```
POST /companion-pets/from-adoption/{app_id}
  -> Validate adoption is APPROVED or COMPLETED
  -> Create CompanionPet linked to adoption + original dog profile
```

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| Safety tag scan | Notifications | Push to pet owner |
| Medical record creation | PetReminder | Auto-creates reminder |
| Reminder due (daily cron) | Notifications | Push + in-app to owner |
| Adoption completed | CompanionPet | Can create pet from adoption |
