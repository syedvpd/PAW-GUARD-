# Shelter Module

Facility management, kennel assignment, dual-confirm transfers, sanitation lifecycle, and daily care logs.

---

## Architecture

```
shelter/
  router.py          # 24 endpoints
  service.py         # ShelterService (facilities, kennels, transfers, care)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## Hierarchy

```
Facility (shelter/clinic/foster_home/partner)
  └── Section (quarantine/isolation/surgical/puppy/general/adoption)
       └── Kennel (capacity, sanitation_state)
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `ShelterFacility` | `shelter_facilities` | Facility: name, address, GPS, capacity, type |
| `ShelterSection` | `shelter_sections` | Section within facility |
| `Kennel` | `kennels` | Individual kennel with capacity + sanitation |
| `FacilityTransfer` | `facility_transfers` | Dual-confirm transfer between facilities |
| `DailyCareLog` | `daily_care_logs` | Dog care record with inventory consumption |
| `KennelCleaningLog` | `kennel_cleaning_logs` | Cleaning audit trail |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/shelter/facilities` | `shelter:update` | Create facility |
| GET | `/shelter/facilities` | `shelter:read` | List facilities |
| GET | `/shelter/facilities/{id}` | `shelter:read` | Get facility |
| PUT | `/shelter/facilities/{id}` | `shelter:update` | Update facility |
| PUT | `/shelter/facilities/{id}/status` | `shelter:update` | Update status |
| DELETE | `/shelter/facilities/{id}` | `shelter:update` | Soft delete |
| POST | `/shelter/facilities/{id}/sections` | `shelter:update` | Create section |
| GET | `/shelter/facilities/{id}/sections` | `shelter:read` | List sections |
| POST | `/shelter/sections/{id}/kennels` | `shelter:update` | Create kennel |
| GET | `/shelter/sections/{id}/kennels` | `shelter:read` | List kennels |
| POST | `/shelter/kennels/{id}/assign/{dog_id}` | `shelter:update` | Assign dog to kennel |
| PUT | `/shelter/kennels/{id}/sanitation` | `shelter:update` | Update sanitation status |
| POST | `/shelter/kennels/{id}/cleaning-logs` | `shelter:update` | Log cleaning |
| GET | `/shelter/kennels/{id}/cleaning-logs` | `shelter:read` | List cleaning logs |
| POST | `/shelter/transfers` | `shelter:update` | Request transfer |
| GET | `/shelter/transfers` | `shelter:read` | List transfers |
| POST | `/shelter/transfers/{id}/confirm-sender` | `shelter:update` | Confirm sender side |
| POST | `/shelter/transfers/{id}/confirm-receiver` | `shelter:update` | Confirm receiver side |
| POST | `/shelter/care-logs` | `shelter:update` | Submit care log |
| GET | `/shelter/dogs/{id}/care-logs` | `shelter:read` | List care logs for dog |
| POST | `/shelter/facilities/bulk/delete` | `shelter:update` | Bulk soft delete |
| POST | `/shelter/facilities/bulk/status` | `shelter:update` | Bulk status |

## Kennel Assignment

```
POST /shelter/kennels/{kennel_id}/assign/{dog_id}
  -> Row-lock kennel (SELECT FOR UPDATE)
  -> Sanitation check: FAIL if NEEDS_CLEANING / DISINFECTING / OUT_OF_SERVICE
  -> Capacity check: FAIL if occupancy >= capacity
  -> Update dog: shelter_facility_id, kennel_id, status=SHELTER
  -> Audit: KENNEL_ASSIGNED
```

## Sanitation Lifecycle

```
CLEAN ──> NEEDS_CLEANING ──> DISINFECTING ──> OUT_OF_SERVICE
   ^              |
   └──clean───────┘  (cleaning log resets to CLEAN)
```

Cleaning log creates `KennelCleaningLog` and resets `kennel.sanitation_state = CLEAN`.

## Dual-Confirm Transfer

```
POST /shelter/transfers {dog_id, from_facility_id, to_facility_id}
  -> Create FacilityTransfer (status=PENDING)

POST /shelter/transfers/{id}/confirm-sender
  -> sender_confirmed_at = now
  -> If BOTH sides confirmed:
     -> dog.shelter_facility_id = destination
     -> dog.kennel_id = None (must re-assign at destination)
     -> transfer.status = COMPLETED

POST /shelter/transfers/{id}/confirm-receiver
  -> receiver_confirmed_at = now
  -> Same completion logic
```

**Rules:**
- Same user CANNOT confirm both sides
- Sender and receiver must be different users

## Daily Care Log

```
POST /shelter/care-logs {dog_id, exercise_hours, inventory_consumptions?}
  -> Create DailyCareLog
  -> If inventory_consumptions provided:
     -> InventoryService.record_movement(CHECK_OUT, reference_type="daily_care_log")
```

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| Care log with consumptions | Inventory | `CHECK_OUT` movements |
| Kennel assignment | Dog | Updates `dog.shelter_facility_id`, `dog.kennel_id` |
| Transfer completion | Dog | Moves dog to destination facility |
