# Constraints and Data Integrity

## Overview

This document describes the constraints and data integrity policies enforced at the database level in the PawGuard backend. These constraints ensure data consistency, prevent invalid states, and maintain referential integrity across all modules.

---

## Constraint Naming Convention

All constraints follow the naming convention defined in `src/pawguard/db/base.py`:

```
{type}_{table_name}_{column_name}
```

| Type | Prefix | Example |
|------|--------|---------|
| Primary Key | `pk_` | `pk_users` |
| Unique | `uq_` | `uq_users_email` |
| Foreign Key | `fk_` | `fk_dog_profiles_rescue_case_id_rescue_requests` |
| Check | `ck_` | `ck_dog_profiles_age_months_range` |

---

## Primary Key Constraints

Every table has a UUID primary key:

```sql
ALTER TABLE users ADD CONSTRAINT pk_users PRIMARY KEY (id);
ALTER TABLE dog_profiles ADD CONSTRAINT pk_dog_profiles PRIMARY KEY (id);
-- ... (all tables)
```

Primary keys are generated via `gen_random_uuid()` and are immutable.

---

## Unique Constraints

### Auth Module

| Table | Column(s) | Constraint Name | Description |
|-------|-----------|-----------------|-------------|
| `users` | `email` | `uq_users_email` | One account per email |
| `roles` | `name` | `uq_roles_name` | Unique role names |
| `permissions` | `code` | `uq_permissions_code` | Unique permission codes |
| `oauth_accounts` | `provider`, `provider_user_id` | `ix_oauth_accounts_provider` | One link per provider account |
| `refresh_tokens` | `token_hash` | `uq_refresh_tokens_token_hash` | One record per token |
| `password_reset_tokens` | `token_hash` | `uq_password_reset_tokens_token_hash` | One record per token |
| `email_verification_tokens` | `token_hash` | `uq_email_verification_tokens_token_hash` | One record per token |

### Dog Module

| Table | Column(s) | Constraint Name | Description |
|-------|-----------|-----------------|-------------|
| `dog_profiles` | `registration_number` | `uq_dog_profiles_registration_number` | Unique registration ID |
| `dog_profiles` | `microchip_id` | `uq_dog_profiles_microchip_id` | Unique microchip number |

### Rescue Module

| Table | Column(s) | Constraint Name | Description |
|-------|-----------|-----------------|-------------|
| `rescue_requests` | `ticket_number` | `uq_rescue_requests_ticket_number` | Unique ticket identifier |
| `rescue_dispatches` | `rescue_request_id` | `uq_rescue_dispatches_rescue_request_id` | One dispatch per request |
| `rescue_dispatch_agents` | `dispatch_id`, `agent_id` | `uq_rescue_dispatch_agents_dispatch_agent` | One assignment per agent per dispatch |

### Medical Module

| Table | Column(s) | Constraint Name | Description |
|-------|-----------|-----------------|-------------|
| `vaccine_protocols` | `name` | `uq_vaccine_protocols_name` | Unique protocol names |

### Shelter Module

| Table | Column(s) | Constraint Name | Description |
|-------|-----------|-----------------|-------------|
| `shelter_facilities` | `name` | `uq_shelter_facilities_name` | Unique facility names |

### Fleet Module

| Table | Column(s) | Constraint Name | Description |
|-------|-----------|-----------------|-------------|
| `vehicles` | `license_plate` | `uq_vehicles_license_plate` | Unique license plates |

---

## Foreign Key Constraints

Foreign keys enforce referential integrity between tables. The `ON DELETE` behavior determines what happens when the referenced record is deleted.

### ON DELETE CASCADE

Used for owned records that should be removed when the parent is deleted:

| Source Table | Target Table | Column | Effect |
|-------------|--------------|--------|--------|
| `user_roles` | `users` | `user_id` | Delete user's roles |
| `user_roles` | `roles` | `role_id` | Delete role's users |
| `role_permissions` | `roles` | `role_id` | Delete role's permissions |
| `role_permissions` | `permissions` | `permission_id` | Delete permission's roles |
| `user_sessions` | `users` | `user_id` | Delete user's sessions |
| `refresh_tokens` | `user_sessions` | `session_id` | Delete session's tokens |
| `mfa_devices` | `users` | `user_id` | Delete user's MFA devices |
| `password_reset_tokens` | `users` | `user_id` | Delete user's reset tokens |
| `email_verification_tokens` | `users` | `user_id` | Delete user's verification tokens |
| `oauth_accounts` | `users` | `user_id` | Delete user's OAuth accounts |
| `dog_weight_logs` | `dog_profiles` | `dog_id` | Delete dog's weight logs |
| `dog_activity_logs` | `dog_profiles` | `dog_id` | Delete dog's activity logs |
| `rescue_dispatches` | `rescue_requests` | `rescue_request_id` | Delete request's dispatch |
| `rescue_dispatch_agents` | `rescue_dispatches` | `dispatch_id` | Delete dispatch's agents |
| `rescue_reports` | `rescue_requests` | `rescue_request_id` | Delete request's reports |
| `rescue_reports` | `users` | `agent_id` | Delete agent's reports |
| `clinical_exams` | `dog_profiles` | `dog_id` | Delete dog's exams |
| `clinical_exams` | `users` | `vet_id` | Delete vet's exams |
| `medical_treatments` | `dog_profiles` | `dog_id` | Delete dog's treatments |
| `medical_treatments` | `users` | `vet_id` | Delete vet's treatments |
| `vaccination_records` | `dog_profiles` | `dog_id` | Delete dog's vaccinations |
| `vaccination_records` | `users` | `administered_by` | Delete admin's records |
| `prescriptions` | `dog_profiles` | `dog_id` | Delete dog's prescriptions |
| `prescriptions` | `users` | `vet_id` | Delete vet's prescriptions |
| `medication_administration_logs` | `dog_profiles` | `dog_id` | Delete dog's administrations |
| `medication_administration_logs` | `users` | `administered_by_id` | Delete admin's logs |
| `medical_clearances` | `dog_profiles` | `dog_id` | Delete dog's clearances |
| `medical_clearances` | `users` | `authorized_by_id` | Delete authorizer's clearances |
| `adoption_applications` | `dog_profiles` | `dog_id` | Delete dog's applications |
| `adoption_applications` | `users` | `adopter_id` | Delete adopter's applications |
| `adoption_scores` | `adoption_applications` | `application_id` | Delete application's scores |
| `adoption_scores` | `users` | `scored_by_id` | Delete scorer's scores |
| `adoption_follow_ups` | `adoption_applications` | `adoption_application_id` | Delete application's follow-ups |
| `shelter_sections` | `shelter_facilities` | `facility_id` | Delete facility's sections |
| `kennels` | `shelter_sections` | `section_id` | Delete section's kennels |
| `facility_transfers` | `dog_profiles` | `dog_id` | Delete dog's transfers |
| `facility_transfers` | `shelter_facilities` | `from_facility_id` | Delete source transfers |
| `facility_transfers` | `shelter_facilities` | `to_facility_id` | Delete destination transfers |
| `facility_transfers` | `users` | `transferred_by` | Delete initiator's transfers |
| `daily_care_logs` | `dog_profiles` | `dog_id` | Delete dog's care logs |
| `daily_care_logs` | `users` | `logged_by` | Delete logger's logs |
| `kennel_cleaning_logs` | `kennels` | `kennel_id` | Delete kennel's cleaning logs |
| `kennel_cleaning_logs` | `users` | `cleaned_by` | Delete cleaner's logs |
| `fleet_maintenances` | `vehicles` | `vehicle_id` | Delete vehicle's maintenance |
| `fuel_logs` | `vehicles` | `vehicle_id` | Delete vehicle's fuel logs |

### ON DELETE SET NULL

Used for optional references that should be preserved when the referenced record is deleted:

| Source Table | Target Table | Column | Effect |
|-------------|--------------|--------|--------|
| `refresh_tokens` | `refresh_tokens` | `rotated_to_id` | Set to NULL |
| `auth_audit_logs` | `users` | `user_id` | Set to NULL |
| `dog_profiles` | `rescue_requests` | `rescue_case_id` | Set to NULL |
| `dog_profiles` | `shelter_facilities` | `shelter_facility_id` | Set to NULL |
| `dog_profiles` | `shelter_sections` | `section_id` | Set to NULL |
| `dog_profiles` | `kennels` | `kennel_id` | Set to NULL |
| `dog_profiles` | `foster_profiles` | `foster_home_id` | Set to NULL |
| `dog_weight_logs` | `users` | `measured_by` | Set to NULL |
| `dog_activity_logs` | `users` | `actor_id` | Set to NULL |
| `rescue_requests` | `users` | `coordinator_id` | Set to NULL |
| `rescue_dispatches` | `users` | `assigned_driver_id` | Set to NULL |
| `rescue_dispatches` | `vehicles` | `assigned_vehicle_id` | Set to NULL |
| `medication_administration_logs` | `prescriptions` | `prescription_id` | Set to NULL |
| `facility_transfers` | `users` | `sender_confirmed_by` | Set to NULL |
| `facility_transfers` | `users` | `receiver_confirmed_by` | Set to NULL |
| `vehicles` | `users` | `primary_driver_id` | Set to NULL |
| `equipment_checkouts` | `users` | `assigned_to_agent_id` | Set to NULL |
| `equipment_checkouts` | `vehicles` | `assigned_to_vehicle_id` | Set to NULL |
| `equipment_checkouts` | `rescue_dispatches` | `rescue_dispatch_id` | Set to NULL |
| `fuel_logs` | `users` | `filled_by_id` | Set to NULL |

---

## Check Constraints

### Data Type Constraints

| Table | Column | Constraint | Description |
|-------|--------|------------|-------------|
| `users` | `email` | `CHECK (length(email) > 0)` | Non-empty email |
| `users` | `full_name` | `CHECK (length(full_name) > 0)` | Non-empty name |
| `dog_profiles` | `age_months` | `CHECK (age_months >= 0 AND age_months <= 600)` | Valid age range |
| `dog_profiles` | `weight` | `CHECK (weight > 0)` | Positive weight |
| `adoption_applications` | `household_members_count` | `CHECK (household_members_count >= 1)` | At least one member |
| `adoption_scores` | `home_environment_score` | `CHECK (score >= 1 AND score <= 10)` | Score 1-10 |
| `adoption_scores` | `pet_care_knowledge_score` | `CHECK (score >= 1 AND score <= 10)` | Score 1-10 |
| `adoption_scores` | `financial_readiness_score` | `CHECK (score >= 1 AND score <= 10)` | Score 1-10 |
| `adoption_scores` | `lifestyle_compatibility_score` | `CHECK (score >= 1 AND score <= 10)` | Score 1-10 |
| `clinical_exams` | `body_condition_score` | `CHECK (score >= 1 AND score <= 9)` | BCS 1-9 |
| `shelter_facilities` | `total_capacity` | `CHECK (total_capacity >= 1)` | At least 1 |
| `shelter_sections` | `capacity` | `CHECK (capacity >= 1)` | At least 1 |
| `kennels` | `capacity` | `CHECK (capacity >= 1)` | At least 1 |
| `daily_care_logs` | `exercise_hours` | `CHECK (exercise_hours >= 0 AND exercise_hours <= 24)` | Valid hours |
| `fleet_maintenances` | `cost` | `CHECK (cost >= 0)` | Non-negative cost |
| `fuel_logs` | `volume_litres` | `CHECK (volume_litres > 0)` | Positive volume |
| `fuel_logs` | `cost` | `CHECK (cost >= 0)` | Non-negative cost |
| `adoption_follow_ups` | `due_day` | `CHECK (due_day >= 30 AND due_day <= 180)` | 30-180 days |

---

## Enum Constraints

Several columns use string types with application-level enum validation. The valid values are defined in the SQLAlchemy models as `StrEnum` classes.

### Dog Module

| Column | Enum Class | Valid Values |
|--------|------------|--------------|
| `dog_profiles.status` | `DogStatus` | `rescued`, `clinic`, `shelter`, `fostered`, `adopted` |
| `dog_profiles.gender` | `DogGender` | `male`, `female`, `unknown` |
| `dog_profiles.breed_classification` | `DogBreedClassification` | `pure`, `mix`, `unknown` |
| `dog_profiles.temperament` | `DogTemperament` | `friendly`, `timid_fearful`, `aggressive`, `high_energy`, `pack_compatible`, `cat_child_safe`, `unknown` |
| `dog_profiles.ear_shape` | `DogEarShape` | `pricked`, `floppy`, `semi_pricked`, `rose`, `button`, `unknown` |
| `dog_profiles.tail_type` | `DogTailType` | `straight`, `curled`, `docked`, `long`, `bobtail`, `unknown` |
| `dog_activity_logs.event_type` | `DogActivityEventType` | `registered`, `updated`, `status_changed`, `deleted`, `weight_recorded`, `bulk_status_updated`, `bulk_deleted` |

### Rescue Module

| Column | Enum Class | Valid Values |
|--------|------------|--------------|
| `rescue_requests.status` | `RescueStatus` | `reported`, `verified`, `dispatched`, `located`, `rescued`, `admitted`, `rejected` |
| `rescue_requests.physical_condition` | `RescuePhysicalCondition` | `critical_life_threatening`, `fractured_injured`, `contagious_sick`, `malnourished`, `abandoned_stray`, `unknown` |
| `rescue_requests.severity` | `RescueSeverity` | `critical`, `high`, `medium`, `low` |
| `rescue_dispatches.failure_reason` | `RescueFailureReason` | `animal_fled`, `area_inaccessible`, `false_report`, `local_intervention_blocked`, `other` |
| `rescue_dispatches.escalation_type` | `RescueEscalationType` | `backup_personnel`, `vet_transport`, `law_enforcement`, `other` |

### Adoption Module

| Column | Enum Class | Valid Values |
|--------|------------|--------------|
| `adoption_applications.status` | `AdoptionStatus` | `submitted`, `screening`, `interview`, `home_check`, `approved`, `completed`, `rejected`, `vetting` (deprecated) |
| `adoption_follow_ups.status` | `FollowUpStatus` | `pending`, `submitted`, `overdue` |

### Shelter Module

| Column | Enum Class | Valid Values |
|--------|------------|--------------|
| `shelter_facilities.status` | `FacilityStatus` | `active`, `inactive`, `maintenance` |
| `shelter_facilities.facility_type` | `FacilityType` | `shelter`, `clinic`, `foster_home`, `partner` |
| `shelter_sections.section_type` | `SectionType` | `quarantine`, `isolation`, `surgical`, `puppy`, `general`, `adoption` |
| `kennels.sanitation_state` | `KennelSanitationState` | `clean`, `needs_cleaning`, `disinfecting`, `out_of_service` |
| `facility_transfers.status` | `TransferStatus` | `pending`, `completed`, `cancelled` |

### Fleet Module

| Column | Enum Class | Valid Values |
|--------|------------|--------------|
| `vehicles.status` | `VehicleStatus` | `active`, `in_maintenance`, `out_of_service` |
| `vehicles.vehicle_type` | `VehicleType` | `rescue_van`, `ambulance`, `mobile_vet_unit`, `utility`, `other` |

---

## Application-Level Constraints

### Password Strength

Defined in `src/pawguard/modules/auth/schemas.py`:

```python
PASSWORD_MIN_LENGTH = 10

def _validate_password_strength(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if not any(c.isupper() for c in value):
        raise ValueError("Password must contain an uppercase letter.")
    if not any(c.islower() for c in value):
        raise ValueError("Password must contain a lowercase letter.")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain a digit.")
    return value
```

### Phone Number Format

Defined in `src/pawguard/modules/auth/schemas.py`:

```python
PHONE_REGEX = re.compile(r"^\+?[1-9]\d{6,14}$")
INDIAN_PHONE_REGEX = re.compile(r"^\+91[6-9]\d{9}$")
```

### Email Format

Pydantic's `EmailStr` type validates email format using the `email-validator` library.

### Name Format

```python
NAME_REGEX = re.compile(r"^[a-zA-Z\s\.\'\-]+$")
```

---

## Transaction Isolation

The database uses PostgreSQL's default transaction isolation level (READ COMMITTED). For operations requiring stronger guarantees:

1. **Optimistic Locking:** Use `updated_at` timestamps for concurrent update detection
2. **Serializable Transactions:** Use for critical state transitions (adoption approval, rescue status changes)
3. **Row-Level Locking:** Use `SELECT ... FOR UPDATE` when reading and modifying the same row

---

## Data Integrity Patterns

### Soft Delete Integrity

Soft-deleted records are excluded from all queries via application-level filtering. The `deleted_at` column serves as both a deletion marker and timestamp.

### Audit Trail Integrity

The `auth_audit_logs` table is append-only. Records are never updated or deleted, providing a complete audit trail.

### Token Rotation Chain

Refresh tokens form a rotation chain via `rotated_to_id`, allowing detection of token reuse and session hijacking.

### State Machine Integrity

Adoption and rescue status transitions are validated at the application level to prevent invalid state changes.
