# Foster Module

Foster home management — applications, placements, daily progress tracking, supply dispatch, and foster-to-adoption conversion.

---

## Architecture

```
foster/
  router.py          # 14 endpoints
  service.py         # FosterService (lifecycle, capacity, conversion)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## State Machine

```
APPLIED ──approve──> APPROVED ──deactivate──> INACTIVE
   │
   └──reject──> REJECTED
```

**Role granting:** `foster_family` role granted on APPROVED (not at application time).

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `FosterProfile` | `foster_profiles` | Application: status, capacity, availability |
| `FosterPlacement` | `foster_placements` | Active dog placement (1:1 with dog) |
| `FosterProgressLog` | `foster_progress_logs` | Daily: weight, behavior, feeding, mood (1-5) |
| `FosterSupplyDispatch` | `foster_supply_dispatches` | Items sent to foster home |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/fosters/apply` | Auth (rate-limited) | Submit application |
| PUT | `/fosters/{id}` | `foster:update` | Update / approve / reject |
| DELETE | `/fosters/{id}` | `foster:update` | Soft delete |
| POST | `/fosters/{id}/placements` | `foster:approve` | Place dog |
| POST | `/fosters/placements/{id}/return` | `foster:approve` | Return dog |
| GET | `/fosters` | `foster:read` | List profiles |
| POST | `/fosters/placements/{id}/progress` | Owner or `foster:approve` | Log daily progress |
| GET | `/fosters/placements/{id}/progress` | Owner or `foster:update` | View progress |
| POST | `/fosters/placements/{id}/supplies` | `foster:approve` | Dispatch supplies |
| GET | `/fosters/placements/{id}/supplies` | Owner or `foster:update` | View supplies |
| POST | `/fosters/placements/{id}/convert-to-adopt` | `foster:approve` | Convert to adoption |
| POST | `/fosters/bulk/delete` | `foster:update` | Bulk soft delete |

## Key Flows

### Place Dog
```
POST /fosters/{foster_id}/placements {dog_id, notes?}
  -> Validate foster is APPROVED
  -> Validate capacity (active_count < max_capacity)
  -> Validate dog exists, not ADOPTED, no active placement
  -> Create FosterPlacement (is_active=True)
  -> foster.active_count += 1
  -> If at capacity: foster.is_available = False
  -> dog.status = FOSTERED
  -> Push notification to foster family
  -> Audit: FOSTER_PLACEMENT_CREATED
```

### Return Dog
```
POST /fosters/placements/{id}/return
  -> placement.is_active = False, returned_at = now
  -> foster.active_count -= 1 (floor 0)
  -> If below capacity: foster.is_available = True
  -> dog.status = SHELTER
  -> Push notification to foster family
  -> Audit: FOSTER_PLACEMENT_ENDED
```

### Foster-to-Adoption Conversion
```
POST /fosters/placements/{id}/convert-to-adopt
  -> Dog row lock (SELECT FOR UPDATE)
  -> Validate dog.is_adoptable = True (medical clearance required)
  -> Validate medical clearance exists and not expired
  -> Validate no existing approved application
  -> Create AdoptionApplication in COMPLETED status (skips vetting)
  -> Generate agreement PDF (fee=0.0)
  -> End placement (returned, capacity decremented)
  -> dog.status = ADOPTED
  -> Dual audit: ADOPTION_SUBMITTED + FOSTER_PLACEMENT_ENDED
```

## Capacity Management

| Field | Purpose |
|-------|---------|
| `max_capacity` | Set at application, updatable |
| `active_count` | Maintained by service (increment on place, decrement on return) |
| `is_available` | Auto-toggled: False when at capacity, True when below |

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| Approval | Auth | Grants `foster_family` role |
| Place dog | Dog | Sets `dog.status = FOSTERED` |
| Return dog | Dog | Sets `dog.status = SHELTER` |
| Convert to adopt | Adoption | Creates COMPLETED adoption + agreement PDF |
| Place/Return/Convert | Notifications | Push notifications to foster family |
