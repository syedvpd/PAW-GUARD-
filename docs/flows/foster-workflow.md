# Foster Workflow

## Overview

The foster workflow manages temporary dog placements with approved foster homes. The implementation is in `src/pawguard/modules/foster/service.py`.

## State Machine

```
APPLIED --> APPROVED --> ACTIVE PLACEMENT --> RETURNED
    |                                  |
    +--> REJECTED                      +--> CONVERTED_TO_ADOPT --> Adoption review
```

### Status Definitions

| Status | Description |
|--------|-------------|
| `applied` | Foster application submitted |
| `approved` | Application approved, eligible for placements |
| `rejected` | Application rejected |
| `inactive` | Approved foster temporarily unavailable; cannot have active placements |

## Data Models

### FosterProfile
- `user_id`: Foster parent (unique)
- `status`: Application status
- `preferences`: Accepted dog types (e.g., "Pups, Medical Recovery")
- `max_capacity`: Maximum concurrent placements
- `active_count`: Current active placements
- `is_available`: Available for new placements
- `notes`: Additional notes

### FosterPlacement
- `foster_id`: Foster profile
- `dog_id`: Dog being fostered
- `placed_at`: Placement start datetime
- `returned_at`: Placement end datetime (nullable)
- `is_active`: Currently active
- `notes`: Placement notes
- `status`: `active`, `returned`, or `converted_to_adopt`
- `adoption_application_id`: linked fast-track application when converted

### FosterProgressLog
- `placement_id`: Associated placement
- `tracked_by_id`: Staff/foster parent logging
- `weight_kg`: Dog weight
- `behavior_notes`: Behavioral observations
- `feeding_notes`: Feeding schedule/details
- `medication_notes`: Medication administration
- `exercise_minutes`: Exercise duration
- `photo_urls`: Progress photos
- `mood_rating`: Subjective mood rating
- `notes`: Additional notes
- `logged_at`: Log timestamp

### FosterSupplyDispatch
- `placement_id`: Associated placement
- `dispatched_by_id`: Staff member dispatching
- `item_type`: food, crate, medication, bedding, toys, other
- `description`: Item description
- `quantity`: Number of items
- `dispatched_at`: Dispatch timestamp

## Workflow Steps

### 1. Submit Foster Application

**Actor**: Public user (authenticated)

**Endpoint**: `POST /fosters/apply`

**Data Required**:
- Preferences (accepted dog types)
- Max capacity
- Additional notes

**Side Effects**:
- Foster profile created with `APPLIED` status
- Audit event (`foster_application_submitted`)

### 2. Review Application

**Actor**: Foster coordinator

**Endpoint**: `PUT /fosters/{id}`

**Transition**: `APPLIED` -> `APPROVED` or `REJECTED`. Approval requires a
passed background check, verified references, and a passed home inspection.

### 3. Place Dog

**Actor**: Foster coordinator

**Endpoint**: `POST /fosters/{id}/placements`

**Data Required**:
- Dog ID
- Placement notes

**Validation**:
- Foster profile must be `APPROVED`
- `active_count` < `max_capacity`
- Dog must have a current approved medical clearance (or veterinarian exception)
- Dog must not already be fostered, adopted, or allocated by another active placement

**Side Effects**:
- Foster placement created
- Dog status updated to `FOSTERED`
- `active_count` incremented
- Audit event (`foster_placement_created`)

### 4. Log Progress

**Actor**: Foster parent or staff

**Endpoint**: `POST /fosters/placements/{placement_id}/progress`

**Data Captured**:
- Weight measurement
- Behavior notes
- Feeding notes
- Medication notes
- Exercise duration
- Photos
- Mood rating

### 5. Dispatch Supplies

**Actor**: Staff

**Endpoint**: `POST /fosters/placements/{placement_id}/supplies`

**Data Required**:
- Item type (food, crate, medication, bedding, toys, other)
- Description
- Quantity

**Side Effects**:
- Supply dispatch recorded
- Audit event (`foster_supply_dispatched`)

### 6. End Placement

**Actor**: Foster coordinator

**Endpoint**: `POST /fosters/placements/{placement_id}/return`

**Data Required**:
- Return notes

**Side Effects**:
- Placement `is_active` set to false
- `returned_at` timestamp set
- `active_count` decremented
- Dog status updated (back to `SHELTER` or `ADOPTED`)
- Audit event (`foster_placement_ended`)

### 7. Foster-to-Adopt

**Endpoint**: `POST /fosters/placements/{placement_id}/convert-to-adopt`

The endpoint creates a pre-populated adoption application with `submitted`
status and links it to the placement. It does not mark the dog adopted or
bypass adoption review. The ordinary adoption workflow performs approval,
exclusive dog locking, agreement generation, handover, and final adoption.

## Kennel Exclusivity Constraint

Dogs cannot be simultaneously in a kennel and foster home. The database enforces this with a check constraint:
- If `kennel_id` is set, `foster_home_id` must be null
- If `foster_home_id` is set, `kennel_id` must be null

## Supply Item Types

| Type | Description |
|------|-------------|
| `food` | Dog food |
| `crate` | Transport/rest crate |
| `medication` | Medications |
| `bedding` | Bedding materials |
| `toys` | Enrichment toys |
| `other` | Other supplies |

## Security

- Foster parents can only view their own placements and progress logs
- Coordinators can view all foster data
- Supply dispatch requires staff permission
- Audit trail for all state changes
