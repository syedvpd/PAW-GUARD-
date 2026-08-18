# Entity Relationships

## Overview

This document describes the foreign key relationships between all tables in the PawGuard database. Relationships are defined via SQLAlchemy ORM `ForeignKey` declarations and follow consistent patterns for cascade behavior.

---

## Relationship Diagram (Textual)

```
users
  |-- user_roles --> roles
  |-- user_sessions --> refresh_tokens
  |-- oauth_accounts
  |-- mfa_devices
  |-- password_reset_tokens
  |-- email_verification_tokens
  |-- auth_audit_logs
  |
  |-- dog_profiles (as created_by/updated_by)
  |-- dog_weight_logs (as measured_by)
  |-- dog_activity_logs (as actor_id)
  |
  |-- rescue_requests (as coordinator_id)
  |-- rescue_dispatches (as assigned_driver_id)
  |-- rescue_dispatch_agents (as agent_id)
  |-- rescue_reports (as agent_id)
  |
  |-- clinical_exams (as vet_id)
  |-- medical_treatments (as vet_id)
  |-- vaccination_records (as administered_by)
  |-- prescriptions (as vet_id)
  |-- medication_administration_logs (as administered_by_id)
  |-- medical_clearances (as authorized_by_id)
  |
  |-- adoption_applications (as adopter_id)
  |-- adoption_scores (as scored_by_id)
  |
  |-- facility_transfers (as transferred_by, sender_confirmed_by, receiver_confirmed_by)
  |-- daily_care_logs (as logged_by)
  |-- kennel_cleaning_logs (as cleaned_by)
  |
  |-- vehicles (as primary_driver_id)
  |-- fleet_maintenances
  |-- equipment_checkouts (as assigned_to_agent_id)
  |-- fuel_logs (as filled_by_id)

dog_profiles
  |-- rescue_requests (as rescue_case_id)
  |-- shelter_facilities (as shelter_facility_id)
  |-- shelter_sections (as section_id)
  |-- kennels (as kennel_id)
  |-- foster_profiles (as foster_home_id)
  |-- dog_weight_logs
  |-- dog_activity_logs
  |-- clinical_exams
  |-- medical_treatments
  |-- vaccination_records
  |-- prescriptions
  |-- medication_administration_logs
  |-- medical_clearances
  |-- adoption_applications
  |-- facility_transfers
  |-- daily_care_logs
  |-- safety_tags

rescue_requests
  |-- rescue_dispatches (1:1)
  |-- rescue_reports (1:N)
  |-- dog_profiles (1:1)

rescue_dispatches
  |-- rescue_dispatch_agents (1:N)

shelter_facilities
  |-- shelter_sections (1:N)
  |-- dog_profiles (1:N)
  |-- facility_transfers (as from_facility_id, to_facility_id)

shelter_sections
  |-- kennels (1:N)

kennels
  |-- dog_profiles (1:N)
  |-- kennel_cleaning_logs (1:N)

adoption_applications
  |-- adoption_scores (1:N)
  |-- adoption_follow_ups (1:N)

vehicles
  |-- rescue_dispatches (as assigned_vehicle_id)
  |-- equipment_checkouts (as assigned_to_vehicle_id)
  |-- fleet_maintenances (1:N)
  |-- fuel_logs (1:N)

prescriptions
  |-- medication_administration_logs (1:N)
```

---

## Foreign Key Definitions

### Auth Module

| Source Table | Source Column | Target Table | Target Column | On Delete |
|-------------|---------------|--------------|---------------|-----------|
| `user_roles` | `user_id` | `users` | `id` | CASCADE |
| `user_roles` | `role_id` | `roles` | `id` | CASCADE |
| `role_permissions` | `role_id` | `roles` | `id` | CASCADE |
| `role_permissions` | `permission_id` | `permissions` | `id` | CASCADE |
| `user_sessions` | `user_id` | `users` | `id` | CASCADE |
| `refresh_tokens` | `session_id` | `user_sessions` | `id` | CASCADE |
| `refresh_tokens` | `rotated_to_id` | `refresh_tokens` | `id` | SET NULL |
| `mfa_devices` | `user_id` | `users` | `id` | CASCADE |
| `password_reset_tokens` | `user_id` | `users` | `id` | CASCADE |
| `email_verification_tokens` | `user_id` | `users` | `id` | CASCADE |
| `oauth_accounts` | `user_id` | `users` | `id` | CASCADE |
| `auth_audit_logs` | `user_id` | `users` | `id` | SET NULL |

---

### Dog Module

| Source Table | Source Column | Target Table | Target Column | On Delete |
|-------------|---------------|--------------|---------------|-----------|
| `dog_profiles` | `rescue_case_id` | `rescue_requests` | `id` | SET NULL |
| `dog_profiles` | `shelter_facility_id` | `shelter_facilities` | `id` | SET NULL |
| `dog_profiles` | `section_id` | `shelter_sections` | `id` | SET NULL |
| `dog_profiles` | `kennel_id` | `kennels` | `id` | SET NULL |
| `dog_profiles` | `foster_home_id` | `foster_profiles` | `id` | SET NULL |
| `dog_profiles` | `created_by` | `users` | `id` | SET NULL |
| `dog_profiles` | `updated_by` | `users` | `id` | SET NULL |
| `dog_weight_logs` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `dog_weight_logs` | `measured_by` | `users` | `id` | SET NULL |
| `dog_activity_logs` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `dog_activity_logs` | `actor_id` | `users` | `id` | SET NULL |

---

### Rescue Module

| Source Table | Source Column | Target Table | Target Column | On Delete |
|-------------|---------------|--------------|---------------|-----------|
| `rescue_requests` | `coordinator_id` | `users` | `id` | SET NULL |
| `rescue_requests` | `created_by` | `users` | `id` | SET NULL |
| `rescue_requests` | `updated_by` | `users` | `id` | SET NULL |
| `rescue_dispatches` | `rescue_request_id` | `rescue_requests` | `id` | CASCADE |
| `rescue_dispatches` | `assigned_driver_id` | `users` | `id` | SET NULL |
| `rescue_dispatches` | `assigned_vehicle_id` | `vehicles` | `id` | SET NULL |
| `rescue_dispatch_agents` | `dispatch_id` | `rescue_dispatches` | `id` | CASCADE |
| `rescue_dispatch_agents` | `agent_id` | `users` | `id` | CASCADE |
| `rescue_reports` | `rescue_request_id` | `rescue_requests` | `id` | CASCADE |
| `rescue_reports` | `agent_id` | `users` | `id` | CASCADE |

---

### Medical Module

| Source Table | Source Column | Target Table | Target Column | On Delete |
|-------------|---------------|--------------|---------------|-----------|
| `clinical_exams` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `clinical_exams` | `vet_id` | `users` | `id` | CASCADE |
| `medical_treatments` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `medical_treatments` | `vet_id` | `users` | `id` | CASCADE |
| `vaccination_records` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `vaccination_records` | `administered_by` | `users` | `id` | CASCADE |
| `prescriptions` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `prescriptions` | `vet_id` | `users` | `id` | CASCADE |
| `medication_administration_logs` | `prescription_id` | `prescriptions` | `id` | SET NULL |
| `medication_administration_logs` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `medication_administration_logs` | `administered_by_id` | `users` | `id` | CASCADE |
| `medical_clearances` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `medical_clearances` | `authorized_by_id` | `users` | `id` | CASCADE |

---

### Adoption Module

| Source Table | Source Column | Target Table | Target Column | On Delete |
|-------------|---------------|--------------|---------------|-----------|
| `adoption_applications` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `adoption_applications` | `adopter_id` | `users` | `id` | CASCADE |
| `adoption_scores` | `application_id` | `adoption_applications` | `id` | CASCADE |
| `adoption_scores` | `scored_by_id` | `users` | `id` | CASCADE |
| `adoption_follow_ups` | `adoption_application_id` | `adoption_applications` | `id` | CASCADE |

---

### Shelter Module

| Source Table | Source Column | Target Table | Target Column | On Delete |
|-------------|---------------|--------------|---------------|-----------|
| `shelter_sections` | `facility_id` | `shelter_facilities` | `id` | CASCADE |
| `kennels` | `section_id` | `shelter_sections` | `id` | CASCADE |
| `facility_transfers` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `facility_transfers` | `from_facility_id` | `shelter_facilities` | `id` | CASCADE |
| `facility_transfers` | `to_facility_id` | `shelter_facilities` | `id` | CASCADE |
| `facility_transfers` | `transferred_by` | `users` | `id` | CASCADE |
| `facility_transfers` | `sender_confirmed_by` | `users` | `id` | SET NULL |
| `facility_transfers` | `receiver_confirmed_by` | `users` | `id` | SET NULL |
| `daily_care_logs` | `dog_id` | `dog_profiles` | `id` | CASCADE |
| `daily_care_logs` | `logged_by` | `users` | `id` | CASCADE |
| `kennel_cleaning_logs` | `kennel_id` | `kennels` | `id` | CASCADE |
| `kennel_cleaning_logs` | `cleaned_by` | `users` | `id` | CASCADE |

---

### Fleet Module

| Source Table | Source Column | Target Table | Target Column | On Delete |
|-------------|---------------|--------------|---------------|-----------|
| `vehicles` | `primary_driver_id` | `users` | `id` | SET NULL |
| `fleet_maintenances` | `vehicle_id` | `vehicles` | `id` | CASCADE |
| `equipment_checkouts` | `assigned_to_agent_id` | `users` | `id` | SET NULL |
| `equipment_checkouts` | `assigned_to_vehicle_id` | `vehicles` | `id` | SET NULL |
| `equipment_checkouts` | `rescue_dispatch_id` | `rescue_dispatches` | `id` | SET NULL |
| `fuel_logs` | `vehicle_id` | `vehicles` | `id` | CASCADE |
| `fuel_logs` | `filled_by_id` | `users` | `id` | SET NULL |

---

## Cascade Behaviors

### CASCADE

Used for owned records that should be removed when the parent is deleted:
- Dog profile -> weight logs, activity logs
- Rescue request -> dispatches, reports
- Adoption application -> scores, follow-ups
- Facility -> sections, kennels
- Vehicle -> maintenance records, fuel logs

### SET NULL

Used for optional references that should be preserved when the referenced record is deleted:
- User references (created_by, updated_by, actor_id)
- Optional assignments (coordinator_id, primary_driver_id)
- Token chains (rotated_to_id)

### RESTRICT (Implicit)

Primary key references to `users` in critical tables use implicit restrict behavior to prevent accidental deletion of users with active records.
