# Index Strategy

## Overview

This document describes the indexing strategy used across the PawGuard database to optimize query performance. Indexes are designed to support the most common query patterns while minimizing storage and maintenance overhead.

---

## Index Naming Convention

All indexes follow the naming convention defined in `src/pawguard/db/base.py`:

```
ix_{table_name}_{column_name}
```

Composite indexes use multiple column names:

```
ix_{table_name}_{column1}_{column2}
```

---

## Index Categories

### Primary Key Indexes

Every table has a UUID primary key with an implicit unique index:

```
pk_users
pk_dog_profiles
pk_rescue_requests
...
```

### Unique Constraint Indexes

Unique constraints create implicit unique indexes:

| Table | Column(s) | Index Name |
|-------|-----------|------------|
| `users` | `email` | `uq_users_email` |
| `dog_profiles` | `registration_number` | `uq_dog_profiles_registration_number` |
| `dog_profiles` | `microchip_id` | `uq_dog_profiles_microchip_id` |
| `rescue_requests` | `ticket_number` | `uq_rescue_requests_ticket_number` |
| `vehicles` | `license_plate` | `uq_vehicles_license_plate` |
| `oauth_accounts` | `provider`, `provider_user_id` | `ix_oauth_accounts_provider` |
| `rescue_dispatch_agents` | `dispatch_id`, `agent_id` | `uq_rescue_dispatch_agents_dispatch_agent` |
| `vaccine_protocols` | `name` | `uq_vaccine_protocols_name` |
| `shelter_facilities` | `name` | `uq_shelter_facilities_name` |

### Timestamp Indexes

All tables with `TimestampMixin` have indexes on `created_at` and `updated_at`:

| Table | Index Name |
|-------|------------|
| All tables | `ix_{table}_created_at` |
| All tables | `ix_{table}_updated_at` |

### Soft Delete Indexes

All tables with `SoftDeleteMixin` have an index on `deleted_at`:

| Table | Index Name |
|-------|------------|
| All soft-deletable tables | `ix_{table}_deleted_at` |

### Audit Trail Indexes

All tables with `AuditMixin` have indexes on `created_by` and `updated_by`:

| Table | Index Name |
|-------|------------|
| All audited tables | `ix_{table}_created_by` |
| All audited tables | `ix_{table}_updated_by` |

---

## Module-Specific Indexes

### Auth Module

| Table | Column(s) | Index Name | Purpose |
|-------|-----------|------------|---------|
| `users` | `email` (lower) | `ix_users_email_lower` | Case-insensitive email lookup |
| `users` | `fcm_token` | `ix_users_fcm_token` | Push notification token lookup |
| `user_sessions` | `user_id` | `ix_user_sessions_user_id` | Session lookup by user |
| `refresh_tokens` | `token_hash` | `ix_refresh_tokens_token_hash` | Token validation |
| `refresh_tokens` | `session_id` | `ix_refresh_tokens_session_id` | Session token lookup |
| `refresh_tokens` | `rotated_to_id` | `ix_refresh_tokens_rotated_to_id` | Token rotation chain |
| `mfa_devices` | `user_id` | `ix_mfa_devices_user_id` | MFA device lookup |
| `password_reset_tokens` | `user_id` | `ix_password_reset_tokens_user_id` | Reset token lookup |
| `password_reset_tokens` | `token_hash` | `ix_password_reset_tokens_token_hash` | Token validation |
| `email_verification_tokens` | `user_id` | `ix_email_verification_tokens_user_id` | Verification token lookup |
| `email_verification_tokens` | `token_hash` | `ix_email_verification_tokens_token_hash` | Token validation |
| `oauth_accounts` | `user_id` | `ix_oauth_accounts_user_id` | OAuth account lookup |
| `auth_audit_logs` | `user_id`, `created_at` | `ix_auth_audit_logs_user_id_created_at` | User audit trail |
| `auth_audit_logs` | `event_type` | `ix_auth_audit_logs_event_type` | Event type filtering |

### Dog Module

| Table | Column(s) | Index Name | Purpose |
|-------|-----------|------------|---------|
| `dog_profiles` | `registration_number` | `ix_dog_profiles_registration_number` | Registration lookup |
| `dog_profiles` | `microchip_id` | `ix_dog_profiles_microchip_id` | Microchip scan lookup |
| `dog_profiles` | `rescue_case_id` | `ix_dog_profiles_rescue_case_id` | Rescue case link |
| `dog_profiles` | `gender` | `ix_dog_profiles_gender` | Gender filtering |
| `dog_profiles` | `age_months` | `ix_dog_profiles_age_months` | Age range filtering |
| `dog_profiles` | `status` | `ix_dog_profiles_status` | Status filtering |
| `dog_profiles` | `shelter_facility_id` | `ix_dog_profiles_shelter_facility_id` | Facility assignment |
| `dog_profiles` | `section_id` | `ix_dog_profiles_section_id` | Section assignment |
| `dog_profiles` | `kennel_id` | `ix_dog_profiles_kennel_id` | Kennel assignment |
| `dog_profiles` | `foster_home_id` | `ix_dog_profiles_foster_home_id` | Foster home assignment |
| `dog_profiles` | `status`, `shelter_facility_id` | `ix_dog_profiles_status_shelter_facility_id` | Facility capacity queries |
| `dog_profiles` | `status`, `is_adoptable` | `ix_dog_profiles_status_is_adoptable` | Adoption directory |
| `dog_weight_logs` | `dog_id` | `ix_dog_weight_logs_dog_id` | Weight history lookup |
| `dog_weight_logs` | `measured_by` | `ix_dog_weight_logs_measured_by` | Measurement audit |
| `dog_activity_logs` | `dog_id` | `ix_dog_activity_logs_dog_id` | Activity stream lookup |
| `dog_activity_logs` | `actor_id` | `ix_dog_activity_logs_actor_id` | Actor audit |
| `dog_activity_logs` | `event_type` | `ix_dog_activity_logs_event_type` | Event type filtering |

### Rescue Module

| Table | Column(s) | Index Name | Purpose |
|-------|-----------|------------|---------|
| `rescue_requests` | `ticket_number` | `ix_rescue_requests_ticket_number` | Ticket lookup |
| `rescue_requests` | `status` | `ix_rescue_requests_status` | Status filtering |
| `rescue_requests` | `severity` | `ix_rescue_requests_severity` | Severity filtering |
| `rescue_requests` | `is_urgent` | `ix_rescue_requests_is_urgent` | Urgent alert queries |
| `rescue_requests` | `coordinator_id` | `ix_rescue_requests_coordinator_id` | Coordinator assignment |
| `rescue_dispatches` | `rescue_request_id` | `ix_rescue_dispatches_rescue_request_id` | Request lookup (unique) |
| `rescue_dispatches` | `assigned_driver_id` | `ix_rescue_dispatches_assigned_driver_id` | Driver lookup |
| `rescue_dispatches` | `assigned_vehicle_id` | `ix_rescue_dispatches_assigned_vehicle_id` | Vehicle lookup |
| `rescue_dispatches` | `escalation_type` | `ix_rescue_dispatches_escalation_type` | Escalation filtering |
| `rescue_dispatch_agents` | `dispatch_id` | `ix_rescue_dispatch_agents_dispatch_id` | Dispatch agent lookup |
| `rescue_dispatch_agents` | `agent_id` | `ix_rescue_dispatch_agents_agent_id` | Agent case lookup |
| `rescue_reports` | `rescue_request_id` | `ix_rescue_reports_rescue_request_id` | Request reports lookup |
| `rescue_reports` | `agent_id` | `ix_rescue_reports_agent_id` | Agent reports lookup |

### Medical Module

| Table | Column(s) | Index Name | Purpose |
|-------|-----------|------------|---------|
| `clinical_exams` | `dog_id` | `ix_clinical_exams_dog_id` | Dog exam history |
| `clinical_exams` | `vet_id` | `ix_clinical_exams_vet_id` | Vet exam history |
| `medical_treatments` | `dog_id` | `ix_medical_treatments_dog_id` | Dog treatment history |
| `medical_treatments` | `vet_id` | `ix_medical_treatments_vet_id` | Vet treatment history |
| `vaccination_records` | `dog_id` | `ix_vaccination_records_dog_id` | Dog vaccination history |
| `vaccination_records` | `administered_by` | `ix_vaccination_records_administered_by` | Admin audit |
| `prescriptions` | `dog_id` | `ix_prescriptions_dog_id` | Dog prescription history |
| `prescriptions` | `vet_id` | `ix_prescriptions_vet_id` | Vet prescription history |
| `medication_administration_logs` | `prescription_id` | `ix_medication_administration_logs_prescription_id` | Prescription administration |
| `medication_administration_logs` | `dog_id` | `ix_medication_administration_logs_dog_id` | Dog administration history |
| `medication_administration_logs` | `administered_by_id` | `ix_medication_administration_logs_administered_by_id` | Admin audit |
| `medical_clearances` | `dog_id` | `ix_medical_clearances_dog_id` | Dog clearance history |
| `medical_clearances` | `authorized_by_id` | `ix_medical_clearances_authorized_by_id` | Authorization audit |

### Adoption Module

| Table | Column(s) | Index Name | Purpose |
|-------|-----------|------------|---------|
| `adoption_applications` | `dog_id` | `ix_adoption_applications_dog_id` | Dog application history |
| `adoption_applications` | `adopter_id` | `ix_adoption_applications_adopter_id` | Adopter applications |
| `adoption_applications` | `status` | `ix_adoption_applications_status` | Status filtering |
| `adoption_scores` | `application_id` | `ix_adoption_scores_application_id` | Application scores |
| `adoption_scores` | `scored_by_id` | `ix_adoption_scores_scored_by_id` | Scorer audit |
| `adoption_follow_ups` | `adoption_application_id` | `ix_adoption_follow_ups_adoption_application_id` | Application follow-ups |
| `adoption_follow_ups` | `status` | `ix_adoption_follow_ups_status` | Status filtering |

### Shelter Module

| Table | Column(s) | Index Name | Purpose |
|-------|-----------|------------|---------|
| `shelter_facilities` | `status` | `ix_shelter_facilities_status` | Status filtering |
| `shelter_facilities` | `facility_type` | `ix_shelter_facilities_facility_type` | Type filtering |
| `shelter_sections` | `facility_id` | `ix_shelter_sections_facility_id` | Facility sections |
| `shelter_sections` | `section_type` | `ix_shelter_sections_section_type` | Type filtering |
| `kennels` | `section_id` | `ix_kennels_section_id` | Section kennels |
| `facility_transfers` | `dog_id` | `ix_facility_transfers_dog_id` | Dog transfer history |
| `facility_transfers` | `from_facility_id` | `ix_facility_transfers_from_facility_id` | Source facility transfers |
| `facility_transfers` | `to_facility_id` | `ix_facility_transfers_to_facility_id` | Destination facility transfers |
| `facility_transfers` | `transferred_by` | `ix_facility_transfers_transferred_by` | Transfer initiator audit |
| `facility_transfers` | `sender_confirmed_by` | `ix_facility_transfers_sender_confirmed_by` | Sender confirmation audit |
| `facility_transfers` | `receiver_confirmed_by` | `ix_facility_transfers_receiver_confirmed_by` | Receiver confirmation audit |
| `daily_care_logs` | `dog_id` | `ix_daily_care_logs_dog_id` | Dog care history |
| `daily_care_logs` | `logged_by` | `ix_daily_care_logs_logged_by` | Logger audit |
| `kennel_cleaning_logs` | `kennel_id` | `ix_kennel_cleaning_logs_kennel_id` | Kennel cleaning history |
| `kennel_cleaning_logs` | `cleaned_by` | `ix_kennel_cleaning_logs_cleaned_by` | Cleaner audit |

### Fleet Module

| Table | Column(s) | Index Name | Purpose |
|-------|-----------|------------|---------|
| `vehicles` | `license_plate` | `ix_vehicles_license_plate` | Plate lookup |
| `vehicles` | `vehicle_type` | `ix_vehicles_vehicle_type` | Type filtering |
| `vehicles` | `primary_driver_id` | `ix_vehicles_primary_driver_id` | Driver assignment |
| `fleet_maintenances` | `vehicle_id` | `ix_fleet_maintenances_vehicle_id` | Vehicle maintenance history |
| `equipment_checkouts` | `assigned_to_agent_id` | `ix_equipment_checkouts_assigned_to_agent_id` | Agent equipment |
| `equipment_checkouts` | `assigned_to_vehicle_id` | `ix_equipment_checkouts_assigned_to_vehicle_id` | Vehicle equipment |
| `equipment_checkouts` | `rescue_dispatch_id` | `ix_equipment_checkouts_rescue_dispatch_id` | Dispatch equipment |
| `equipment_checkouts` | `expected_return_at` | `ix_equipment_checkouts_expected_return_at` | Overdue equipment |
| `fuel_logs` | `vehicle_id` | `ix_fuel_logs_vehicle_id` | Vehicle fuel history |
| `fuel_logs` | `filled_by_id` | `ix_fuel_logs_filled_by_id` | Filler audit |

---

## Query Optimization Patterns

### Common Query Patterns

1. **Dog Adoption Directory**
   ```sql
   SELECT * FROM dog_profiles
   WHERE status = 'shelter' AND is_adoptable = true
   ORDER BY created_at DESC;
   ```
   Supported by: `ix_dog_profiles_status_is_adoptable`

2. **Rescue Case by Ticket**
   ```sql
   SELECT * FROM rescue_requests
   WHERE ticket_number = 'RES-2026-001';
   ```
   Supported by: `ix_rescue_requests_ticket_number`

3. **User Sessions**
   ```sql
   SELECT * FROM user_sessions
   WHERE user_id = ? AND is_active = true;
   ```
   Supported by: `ix_user_sessions_user_id`

4. **Dog Medical History**
   ```sql
   SELECT * FROM clinical_exams
   WHERE dog_id = ?
   ORDER BY exam_date DESC;
   ```
   Supported by: `ix_clinical_exams_dog_id`

5. **Facility Capacity**
   ```sql
   SELECT * FROM dog_profiles
   WHERE shelter_facility_id = ? AND status = 'shelter';
   ```
   Supported by: `ix_dog_profiles_status_shelter_facility_id`

---

## Performance Considerations

### Index Selectivity

High-selectivity columns (many unique values) benefit most from indexing:
- `email` (unique)
- `registration_number` (unique)
- `ticket_number` (unique)
- `license_plate` (unique)

Low-selectivity columns (few distinct values) may not benefit from single-column indexes:
- `status` (few enum values)
- `gender` (3 values)
- `is_adoptable` (boolean)

For low-selectivity columns, composite indexes are more effective:
- (`status`, `is_adoptable`) for adoption directory
- (`status`, `shelter_facility_id`) for facility queries

### Index Maintenance

- Indexes add overhead to INSERT, UPDATE, and DELETE operations
- Monitor index usage with `pg_stat_user_indexes`
- Remove unused indexes to improve write performance
- Consider partial indexes for frequently filtered subsets

### Partial Indexes (Future Optimization)

For queries that always filter on a specific condition:

```sql
-- Only index active records
CREATE INDEX ix_dog_profiles_active ON dog_profiles (status)
WHERE deleted_at IS NULL;

-- Only index urgent rescue cases
CREATE INDEX ix_rescue_requests_urgent ON rescue_requests (created_at)
WHERE is_urgent = true AND deleted_at IS NULL;
```
