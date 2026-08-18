# Dog Lifecycle

## Overview

The dog lifecycle tracks a dog from initial rescue intake through final resolution (adoption, foster, or long-term shelter stay). The implementation spans multiple modules: rescue, dog, medical, adoption, foster.

## Lifecycle States

```
                    +--> CLINIC --> SHELTER --> FOSTERED --> ADOPTED
                    |
RESCUED (auto) -----+
                    |
                    +--> SHELTER --> ADOPTED
```

### DogStatus Enum

| Status | Description |
|--------|-------------|
| `rescued` | Initial state after rescue admission |
| `clinic` | Under veterinary care |
| `shelter` | In shelter facility |
| `fostered` | In foster home |
| `adopted` | Permanently adopted |

## State Transitions

### RESCUED -> CLINIC
**Trigger**: Rescue admission (auto-created)
**Actor**: System
**Context**: Dog needs immediate veterinary attention

### RESCUED -> SHELTER
**Trigger**: Intake examination complete
**Actor**: Veterinarian or shelter staff
**Context**: Dog cleared for shelter housing

### CLINIC -> SHELTER
**Trigger**: Treatment complete
**Actor**: Veterinarian
**Context**: Dog recovered from treatment

### SHELTER -> FOSTERED
**Trigger**: Foster placement
**Actor**: Foster coordinator
**Context**: Dog placed in approved foster home

### FOSTERED -> SHELTER
**Trigger**: Foster placement ended
**Actor**: Foster coordinator
**Context**: Dog returned from foster

### SHELTER -> ADOPTED
**Trigger**: Adoption completed
**Actor**: Adoption coordinator
**Context**: Dog permanently adopted

## Auto-Creation on Rescue Admission

When a rescue reaches `ADMITTED` status, a `DogProfile` is automatically created:

```python
dog = DogProfile(
    registration_number=f"DOG-{year_str}-{rand_suffix}",
    rescue_case_id=request.id,
    name=f"Unnamed ({request.ticket_number})",
    breed="indie_mix",
    breed_classification=DogBreedClassification.MIX,
    gender=DogGender.UNKNOWN,
    status=DogStatus.RESCUED,
    is_adoptable=False,
)
```

## Dog Profile Fields

### Identity
- `registration_number`: Unique ID (`DOG-YYYY-XXXX`)
- `rescue_case_id`: Linked rescue request
- `microchip_id`: Microchip number (optional)

### Demographics
- `name`: Dog name
- `breed`: Breed string
- `breed_classification`: pure, mix, unknown
- `gender`: male, female, unknown
- `is_spayed_neutered`: Boolean
- `estimated_age`: Text description (e.g., "2 years")
- `age_months`: Numeric age in months (for filtering)
- `weight`: Current weight in kg
- `color`: Coat color

### Temperament
- `temperament`: friendly, timid_fearful, aggressive, high_energy, pack_compatible, cat_child_safe, unknown

### Visual Attributes
- `ear_shape`: pricked, floppy, semi_pricked, rose, button, unknown
- `tail_type`: straight, curled, docked, long, bobtail, unknown
- `distinctive_markers`: Text description of unique features

### Location
- `shelter_facility_id`: Current shelter
- `section_id`: Shelter section
- `kennel_id`: Assigned kennel
- `foster_home_id`: Foster home (mutually exclusive with kennel)

### Status Flags
- `is_adoptable`: Available for adoption
- `is_quarantine_passed`: Passed quarantine

### Media
- `image_urls`: Public gallery URLs

## Weight Tracking

### DogWeightLog
- `dog_id`: Dog being measured
- `measured_by`: Staff member
- `weight`: Weight in kg
- `measured_at`: Measurement timestamp
- `notes`: Notes

**Note**: Profile `weight` holds current weight; `DogWeightLog` stores historical measurements.

## Activity Stream

### DogActivityLog
Immutable, append-only log of all lifecycle events:

| Event Type | Description |
|------------|-------------|
| `registered` | Dog profile created |
| `updated` | Profile updated |
| `status_changed` | Status transition |
| `weight_recorded` | Weight measured |
| `deleted` | Profile soft-deleted |
| `bulk_status_updated` | Bulk status update |
| `bulk_deleted` | Bulk delete |

**Fields**:
- `dog_id`: Dog
- `actor_id`: Staff member (nullable for system actions)
- `event_type`: Event type
- `message`: Human-readable description
- `event_metadata`: Additional context

## Kennel/Foster Exclusivity

Database constraint ensures a dog cannot be simultaneously in a kennel and foster home:
- If `kennel_id` is set, `foster_home_id` must be null
- If `foster_home_id` is set, `kennel_id` must be null

## Adoption Readiness

A dog is marked `is_adoptable=True` when:
1. Medical clearance issued (`medical_clearance` type)
2. Quarantine passed (`is_quarantine_passed=True`)
3. Staff manually marks as adoptable

## Dashboard Cache Invalidation

When a dog profile is created or status changes, dashboard caches are invalidated:
```python
keys = [
    "pawguard:hero_stats",
    "pawguard:transparency_stats",
    "hero_stats",
    "transparency_stats",
    "cache:dashboard:shelter",
    "cache:dashboard:rescue",
    "cache:dashboard:adoption",
    "cache:dashboard:summary",
]
```

## Security

- Dog profiles readable by all authenticated users
- Status changes require appropriate permissions
- Soft-delete pattern (no hard deletes)
- Audit trail for all mutations
- Activity stream is immutable (append-only)
