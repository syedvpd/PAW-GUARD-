# Dog Module

Dog master profiles, lifecycle tracking, weight management, and public adoption portal.

---

## Architecture

```
dog/
  router.py          # 20 endpoints
  service.py         # DogService (registration, updates, activity log)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## State Machine

Dog status is driven by other modules (not enforced at dog level):

```
Rescue Admission ──auto──> RESCUED ──medical treatment──> CLINIC ──medical clearance──> SHELTER ──foster──> FOSTERED ──adoption──> ADOPTED
```

| Status | Set By | Trigger |
|--------|--------|---------|
| `RESCUED` | Rescue module | `POST /rescue/{id}/admitted` |
| `CLINIC` | Medical module | `POST /medical/treatments` |
| `SHELTER` | Medical module | `POST /medical/clearance/{id}` (approved) |
| `FOSTERED` | Foster module | `POST /fosters/{id}/placements` |
| `ADOPTED` | Adoption module | Status update to COMPLETED |

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `DogProfile` | `dog_profiles` | Core record: registration, breed, status, adoptability flags |
| `DogWeightLog` | `dog_weight_logs` | Append-only weight history |
| `DogActivityLog` | `dog_activity_logs` | Immutable lifecycle audit trail |

### Key DogProfile Fields

| Field | Type | Notes |
|-------|------|-------|
| `registration_number` | String(64) | Unique, format `DOG-YYYY-NNNN` |
| `microchip_id` | String(64) | Unique 15-digit, auto-generated `985XXXXXXXXXXXX` |
| `rescue_case_id` | UUID FK | Links to rescue_requests (set on admission) |
| `is_adoptable` | Boolean | **CANNOT be set via profile update** — medical clearance only |
| `is_quarantine_passed` | Boolean | Set by medical clearance |
| `shelter_facility_id` | UUID FK | Current facility assignment |
| `kennel_id` | UUID FK | Current kennel assignment |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/dogs` | `shelter:update` | Register new dog |
| GET | `/dogs` | Public | List dogs (public: adoptable only) |
| GET | `/dogs/{id}` | Optional auth | Get dog (public: adoptable only) |
| GET | `/dogs/{id}/timeline` | `shelter:read` | Immutable activity stream |
| GET | `/dogs/{id}/public-scan` | Public (rate-limited 20/min) | QR scan response |
| GET | `/dogs/{id}/qr-image` | `shelter:update` | Generate QR PNG |
| POST | `/dogs/{id}/weight` | `shelter:update` | Record weight measurement |
| GET | `/dogs/{id}/weights` | `shelter:read` | Weight history |
| PUT | `/dogs/{id}` | `shelter:update` | Update profile |
| PATCH | `/dogs/{id}/status` | `shelter:update` | Update status |
| DELETE | `/dogs/{id}` | `shelter:update` | Soft delete |
| POST | `/dogs/bulk/status-update` | `shelter:update` | Bulk status |
| POST | `/dogs/bulk/delete` | `shelter:update` | Bulk soft delete |
| POST | `/dogs/{id}/safety-tag` | `safety_tag:manage` | Provision safety tag |
| GET | `/dogs/{id}/safety-tag` | `safety_tag:manage` | Get safety tag |
| DELETE | `/dogs/{id}/safety-tag` | `safety_tag:manage` | Revoke safety tag |

## Business Rules

### Registration
1. Duplicate intake prevention: checks name + breed + gender + color + distinctive_markers
2. Auto-generates `registration_number` (DOG-YYYY-NNNN, 5-retry collision loop)
3. Auto-generates `microchip_id` (15-digit, 985 prefix)
4. Breed classification auto-inferred from free text

### Profile Update
- `is_adoptable` CANNOT be set to True via profile update — must use `POST /medical/clearance/{dog_id}`
- Weight changes via profile update also append to `DogWeightLog`

### Public Portal View
- Non-staff callers see ONLY:
  - Dogs where `is_adoptable=True`
  - Dogs NOT in ADOPTED status
  - Internal IDs stripped (microchip, facility, kennel, foster home)

### Activity Log (Immutable)
- Append-only; rows are never updated or deleted
- Cross-module events logged via `record_activity()` function
- Survives soft-deletion

### Cache Invalidation
On every mutation, invalidates: `hero_stats`, `transparency_stats`, all dashboard caches

## Cross-Module Interactions

| Source | Trigger | Effect |
|--------|---------|--------|
| Rescue | ADMITTED | Auto-creates DogProfile (status=RESCUED) |
| Medical | Treatment | Sets status=CLINIC |
| Medical | Clearance (approved) | Sets status=SHELTER, is_adoptable=True |
| Foster | Placement | Sets status=FOSTERED |
| Adoption | COMPLETED | Sets status=ADOPTED |
| CompanionPet | Safety tag | Provisions QR tag for the dog |
