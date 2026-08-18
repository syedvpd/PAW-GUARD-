# Database Schema

## Overview

This document provides a comprehensive reference of all database tables in the PawGuard backend, organized by module. Each table listing includes column definitions, types, constraints, and relevant notes.

---

## Auth Module

### users

Stores user account information, credentials, and profile data.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `email` | varchar(255) | No | - | Unique email address |
| `phone` | varchar(32) | Yes | `NULL` | Phone number |
| `full_name` | varchar(255) | No | - | Full name |
| `hashed_password` | varchar(255) | No | - | Bcrypt password hash |
| `is_active` | boolean | No | `true` | Account active flag |
| `is_verified` | boolean | No | `false` | Email verified flag |
| `email_verified_at` | timestamptz | Yes | `NULL` | Email verification timestamp |
| `mfa_enabled` | boolean | No | `false` | MFA enabled flag |
| `failed_login_count` | integer | No | `0` | Consecutive failed login attempts |
| `locked_until` | timestamptz | Yes | `NULL` | Account lock expiration |
| `last_login_at` | timestamptz | Yes | `NULL` | Last successful login |
| `profile_picture_url` | varchar(512) | Yes | `NULL` | Avatar URL |
| `date_of_birth` | date | Yes | `NULL` | Date of birth |
| `gender` | varchar(32) | Yes | `NULL` | Gender |
| `address_line` | varchar(255) | Yes | `NULL` | Street address |
| `city` | varchar(128) | Yes | `NULL` | City |
| `state` | varchar(128) | Yes | `NULL` | State/Province |
| `country` | varchar(128) | Yes | `NULL` | Country |
| `postal_code` | varchar(32) | Yes | `NULL` | Postal/ZIP code |
| `push_notifications_enabled` | boolean | No | `true` | Push notifications flag |
| `fcm_token` | varchar(512) | Yes | `NULL` | Firebase Cloud Messaging token |

**Indexes:**
- `pk_users` (primary key)
- `ix_users_email` (unique)
- `ix_users_email_lower` (functional on lower(email))
- `ix_users_fcm_token`
- `ix_users_created_at`
- `ix_users_updated_at`
- `ix_users_deleted_at`

---

### roles

Role definitions for RBAC.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `name` | varchar(64) | No | - | Unique role name |
| `description` | varchar(255) | Yes | `NULL` | Role description |
| `is_system` | boolean | No | `false` | System-defined role flag |

---

### permissions

Permission codes for RBAC.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `code` | varchar(128) | No | - | Unique permission code (e.g., `rescue:create`) |
| `description` | varchar(255) | Yes | `NULL` | Permission description |

---

### user_roles

Many-to-many: users to roles.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `user_id` | UUID | No | FK to `users.id` (CASCADE) |
| `role_id` | UUID | No | FK to `roles.id` (CASCADE) |

**Primary Key:** (`user_id`, `role_id`)

---

### role_permissions

Many-to-many: roles to permissions.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `role_id` | UUID | No | FK to `roles.id` (CASCADE) |
| `permission_id` | UUID | No | FK to `permissions.id` (CASCADE) |

**Primary Key:** (`role_id`, `permission_id`)

---

### user_sessions

Active user sessions for multi-device management.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `user_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `device_id` | varchar(255) | Yes | `NULL` | Device identifier |
| `device_name` | varchar(255) | Yes | `NULL` | Human-readable device name |
| `device_type` | varchar(16) | No | `unknown` | Device type enum |
| `ip_address` | varchar(64) | Yes | `NULL` | Client IP address |
| `user_agent` | varchar(512) | Yes | `NULL` | Browser user agent |
| `is_active` | boolean | No | `true` | Session active flag |
| `last_used_at` | timestamptz | No | `now()` | Last activity timestamp |
| `expires_at` | timestamptz | No | - | Session expiration |
| `revoked_at` | timestamptz | Yes | `NULL` | Revocation timestamp |
| `revoked_reason` | varchar(255) | Yes | `NULL` | Revocation reason |

---

### refresh_tokens

Refresh token records with rotation chain.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `session_id` | UUID | No | - | FK to `user_sessions.id` (CASCADE) |
| `token_hash` | varchar(64) | No | - | SHA-256 hash of token |
| `issued_at` | timestamptz | No | `now()` | Issue timestamp |
| `expires_at` | timestamptz | No | - | Expiration timestamp |
| `rotated_to_id` | UUID | Yes | `NULL` | FK to `refresh_tokens.id` (SET NULL) |
| `revoked_at` | timestamptz | Yes | `NULL` | Revocation timestamp |
| `revoked_reason` | varchar(255) | Yes | `NULL` | Revocation reason |

---

### mfa_devices

MFA TOTP device registrations.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `user_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `device_type` | varchar(16) | No | `totp` | Device type |
| `secret_encrypted` | text | No | - | Encrypted TOTP secret |
| `is_verified` | boolean | No | `false` | Enrollment verified flag |

---

### password_reset_tokens

Password reset token records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `token_hash` | varchar(64) | No | - | SHA-256 hash of token |
| `expires_at` | timestamptz | No | - | Expiration timestamp |
| `used_at` | timestamptz | Yes | `NULL` | Consumption timestamp |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |

---

### email_verification_tokens

Email verification token records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `token_hash` | varchar(64) | No | - | SHA-256 hash of token |
| `expires_at` | timestamptz | No | - | Expiration timestamp |
| `used_at` | timestamptz | Yes | `NULL` | Consumption timestamp |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |

---

### oauth_accounts

Linked OAuth provider accounts.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `user_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `provider` | varchar(32) | No | - | Provider name (e.g., `google`) |
| `provider_user_id` | varchar(255) | No | - | Provider's user ID |
| `provider_email` | varchar(255) | Yes | `NULL` | Email from provider |
| `display_name` | varchar(255) | Yes | `NULL` | Display name from provider |
| `picture_url` | varchar(512) | Yes | `NULL` | Profile picture URL |

**Unique Index:** (`provider`, `provider_user_id`)

---

### auth_audit_logs

Authentication and system-wide audit trail.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |
| `event_type` | varchar(64) | No | - | Event type code |
| `ip_address` | varchar(64) | Yes | `NULL` | Client IP address |
| `user_agent` | varchar(512) | Yes | `NULL` | Browser user agent |
| `event_metadata` | jsonb | Yes | `NULL` | Additional event context |
| `before_state` | jsonb | Yes | `NULL` | Pre-transition state snapshot |
| `after_state` | jsonb | Yes | `NULL` | Post-transition state snapshot |
| `created_at` | timestamptz | No | `now()` | Event timestamp |

**Composite Index:** (`user_id`, `created_at`)

---

## Dog Module

### dog_profiles

Master dog profile with demographics, visual attributes, and shelter assignment.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `registration_number` | varchar(64) | No | - | Unique registration ID |
| `rescue_case_id` | UUID | Yes | `NULL` | FK to `rescue_requests.id` (SET NULL) |
| `microchip_id` | varchar(64) | Yes | `NULL` | Unique microchip number |
| `name` | varchar(255) | No | - | Dog's name |
| `breed` | varchar(128) | No | `indie_mix` | Breed name |
| `breed_classification` | varchar(16) | No | `unknown` | `pure`, `mix`, `unknown` |
| `gender` | varchar(16) | No | `unknown` | `male`, `female`, `unknown` |
| `is_spayed_neutered` | boolean | No | `false` | Sterilization status |
| `estimated_age` | varchar(64) | Yes | `NULL` | Human-readable age |
| `age_months` | integer | Yes | `NULL` | Numeric age in months |
| `weight` | numeric(5,2) | Yes | `NULL` | Weight in kg |
| `color` | varchar(64) | Yes | `NULL` | Coat color |
| `temperament` | varchar(64) | Yes | `NULL` | Temperament enum |
| `ear_shape` | varchar(32) | Yes | `NULL` | Ear shape enum |
| `tail_type` | varchar(32) | Yes | `NULL` | Tail type enum |
| `distinctive_markers` | text | Yes | `NULL` | Distinguishing features |
| `image_urls` | jsonb | Yes | `NULL` | Photo gallery URLs |
| `status` | varchar(32) | No | `rescued` | Current status |
| `shelter_facility_id` | UUID | Yes | `NULL` | FK to `shelter_facilities.id` (SET NULL) |
| `section_id` | UUID | Yes | `NULL` | FK to `shelter_sections.id` (SET NULL) |
| `kennel_id` | UUID | Yes | `NULL` | FK to `kennels.id` (SET NULL) |
| `foster_home_id` | UUID | Yes | `NULL` | FK to `foster_profiles.id` (SET NULL) |
| `is_adoptable` | boolean | No | `false` | Public adoption flag |
| `is_quarantine_passed` | boolean | No | `false` | Quarantine status |

**Composite Indexes:**
- (`status`, `shelter_facility_id`)
- (`status`, `is_adoptable`)

---

### dog_weight_logs

Immutable weight measurement history.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `measured_by` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |
| `weight` | numeric(5,2) | No | - | Weight in kg |
| `measured_at` | timestamptz | No | - | Measurement timestamp |
| `notes` | text | Yes | `NULL` | Measurement notes |

---

### dog_activity_logs

Append-only lifecycle activity stream.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `actor_id` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |
| `event_type` | varchar(64) | No | - | Event type enum |
| `message` | varchar(512) | No | - | Human-readable event description |
| `event_metadata` | jsonb | Yes | `NULL` | Additional event context |

---

## Rescue Module

### rescue_requests

Emergency rescue cases with reporter information and location.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `ticket_number` | varchar(64) | No | - | Unique ticket identifier |
| `reporter_name` | varchar(255) | No | - | Reporter's name |
| `reporter_phone` | varchar(32) | No | - | Reporter's phone |
| `reporter_alternate_phone` | varchar(32) | Yes | `NULL` | Alternate phone |
| `reporter_email` | varchar(255) | Yes | `NULL` | Reporter's email |
| `is_anonymous` | boolean | No | `false` | Anonymous report flag |
| `location_address` | text | No | - | Incident address |
| `location_landmark` | varchar(255) | Yes | `NULL` | Nearby landmark |
| `latitude` | numeric(9,6) | Yes | `NULL` | GPS latitude |
| `longitude` | numeric(9,6) | Yes | `NULL` | GPS longitude |
| `animal_count` | integer | No | `1` | Number of animals |
| `physical_condition` | varchar(64) | No | `unknown` | Physical condition enum |
| `behavioral_indicators` | text | Yes | `NULL` | Behavioral observations |
| `media_evidence` | jsonb | Yes | `NULL` | Storage object keys |
| `environmental_factors` | text | Yes | `NULL` | Weather/terrain notes |
| `reporter_notes` | text | Yes | `NULL` | Additional reporter notes |
| `status` | varchar(32) | No | `reported` | Current status |
| `severity` | varchar(16) | No | `medium` | Priority level |
| `is_urgent` | boolean | No | `false` | Urgent alert flag |
| `rejection_rationale` | text | Yes | `NULL` | Rejection reason |
| `coordinator_id` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |

---

### rescue_dispatches

Dispatch records linking rescue requests to vehicles and agents.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `rescue_request_id` | UUID | No | - | FK to `rescue_requests.id` (CASCADE), UNIQUE |
| `assigned_driver_id` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |
| `vehicle_id` | varchar(64) | Yes | `NULL` | Legacy vehicle identifier |
| `assigned_vehicle_id` | UUID | Yes | `NULL` | FK to `vehicles.id` (SET NULL) |
| `equipment_details` | text | Yes | `NULL` | Equipment notes |
| `dispatched_at` | timestamptz | No | `now()` | Dispatch timestamp |
| `located_at` | timestamptz | Yes | `NULL` | Location reached timestamp |
| `rescued_at` | timestamptz | Yes | `NULL` | Animal secured timestamp |
| `admitted_at` | timestamptz | Yes | `NULL` | Shelter admission timestamp |
| `failed_at` | timestamptz | Yes | `NULL` | Failure timestamp |
| `failure_reason` | varchar(255) | Yes | `NULL` | Failure reason code |
| `escalation_type` | varchar(32) | Yes | `NULL` | Escalation category |
| `escalation_notes` | text | Yes | `NULL` | Escalation details |
| `notes` | text | Yes | `NULL` | Additional notes |

---

### rescue_dispatch_agents

Association table for multi-agent dispatch teams.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dispatch_id` | UUID | No | - | FK to `rescue_dispatches.id` (CASCADE) |
| `agent_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `role` | varchar(64) | Yes | `NULL` | Agent role in dispatch |

**Unique Constraint:** (`dispatch_id`, `agent_id`)

---

### rescue_reports

Field observation reports from rescue agents.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `rescue_request_id` | UUID | No | - | FK to `rescue_requests.id` (CASCADE) |
| `agent_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `notes` | text | Yes | `NULL` | Observation notes |
| `photos` | jsonb | Yes | `NULL` | Storage object keys (max 5) |

---

## Medical Module

### clinical_exams

Clinical examination records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `vet_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `exam_date` | timestamptz | No | - | Examination date |
| `body_condition_score` | integer | No | - | 1-9 BCS scale |
| `dental_health` | varchar(64) | Yes | `NULL` | Dental assessment |
| `ocular_aural_notes` | text | Yes | `NULL` | Eye/ear notes |
| `coat_condition` | varchar(128) | Yes | `NULL` | Coat assessment |
| `visible_injuries` | text | Yes | `NULL` | External injuries |
| `triage_diagnosis` | text | No | - | Primary diagnosis |

---

### medical_treatments

Treatment and surgery records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `vet_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `treatment_date` | timestamptz | No | - | Treatment date |
| `treatment_type` | varchar(128) | No | - | Type of treatment |
| `description` | text | No | - | Treatment description |
| `anesthesia_log` | text | Yes | `NULL` | Anesthesia details |
| `post_op_notes` | text | Yes | `NULL` | Post-operative notes |

---

### vaccination_records

Vaccination history.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `administered_by` | UUID | No | - | FK to `users.id` (CASCADE) |
| `vaccine_name` | varchar(128) | No | - | Vaccine name |
| `administered_at` | timestamptz | No | - | Administration timestamp |
| `next_due_at` | timestamptz | Yes | `NULL` | Next due date |
| `lot_number` | varchar(64) | Yes | `NULL` | Vaccine lot number |

---

### prescriptions

Medication prescriptions.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `vet_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `drug_name` | varchar(128) | No | - | Medication name |
| `dosage` | varchar(128) | No | - | Dosage instructions |
| `route` | varchar(64) | No | - | Administration route |
| `start_at` | timestamptz | No | - | Start date |
| `end_at` | timestamptz | No | - | End date |
| `is_active` | boolean | No | `true` | Active prescription flag |

---

### medication_administration_logs

Daily nurse sign-off register for medication administrations.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `prescription_id` | UUID | Yes | `NULL` | FK to `prescriptions.id` (SET NULL) |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `medication_name` | varchar(128) | No | - | Medication name |
| `dosage` | varchar(128) | No | - | Dosage administered |
| `route` | varchar(64) | No | - | Administration route |
| `administered_at` | timestamptz | No | - | Administration timestamp |
| `administered_by_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `notes` | text | Yes | `NULL` | Administration notes |

---

### vaccine_protocols

Optional staff-managed vaccination protocols.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `name` | varchar(128) | No | - | Unique protocol name |
| `default_interval_days` | integer | No | - | Default vaccination interval |
| `is_required` | boolean | No | `false` | Required protocol flag |

---

### medical_clearances

Veterinary clearance decisions for adoption/surgery.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `authorized_by_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `clearance_type` | varchar(64) | No | - | Clearance type |
| `status` | varchar(16) | No | - | `approved`, `denied`, `pending` |
| `decision_notes` | text | Yes | `NULL` | Decision rationale |
| `authorized_at` | timestamptz | Yes | `NULL` | Authorization timestamp |
| `expires_at` | timestamptz | Yes | `NULL` | Clearance expiration |

---

## Adoption Module

### adoption_applications

Adoption applications with vetting and approval workflow.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `adopter_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `status` | varchar(32) | No | `submitted` | Application status |
| `residential_status` | varchar(32) | No | - | `owned` or `rented` |
| `has_landlord_approval` | boolean | No | `false` | Landlord approval flag |
| `has_yard_fence` | boolean | No | `false` | Yard fence flag |
| `household_members_count` | integer | No | `1` | Household size |
| `existing_pets_medical_details` | text | Yes | `NULL` | Existing pet details |
| `pet_care_experience` | text | Yes | `NULL` | Pet care experience |
| `vetting_officer_notes` | text | Yes | `NULL` | Officer notes |
| `home_inspection_scheduled_at` | timestamptz | Yes | `NULL` | Scheduled inspection |
| `home_inspection_notes` | text | Yes | `NULL` | Inspection notes |
| `adoption_agreement_url` | varchar(512) | Yes | `NULL` | Agreement document URL |
| `completed_at` | timestamptz | Yes | `NULL` | Completion timestamp |
| `fee_amount` | numeric(10,2) | Yes | `NULL` | Adoption fee |

---

### adoption_scores

Vetting scores for adoption applications.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `application_id` | UUID | No | - | FK to `adoption_applications.id` (CASCADE) |
| `scored_by_id` | UUID | No | - | FK to `users.id` (CASCADE) |
| `home_environment_score` | integer | No | - | Score 1-10 |
| `pet_care_knowledge_score` | integer | No | - | Score 1-10 |
| `financial_readiness_score` | integer | No | - | Score 1-10 |
| `lifestyle_compatibility_score` | integer | No | - | Score 1-10 |
| `overall_score` | numeric(4,1) | No | - | Calculated overall score |
| `recommendation` | varchar(32) | No | - | `approve`, `reject`, `waitlist` |
| `notes` | text | Yes | `NULL` | Scoring notes |
| `scored_at` | timestamptz | No | - | Scoring timestamp |

---

### adoption_follow_ups

Post-adoption follow-up check-ins.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `adoption_application_id` | UUID | No | - | FK to `adoption_applications.id` (CASCADE) |
| `due_day` | integer | No | - | Days after completion |
| `due_at` | timestamptz | No | - | Due date |
| `status` | varchar(16) | No | `pending` | `pending`, `submitted`, `overdue` |
| `submitted_at` | timestamptz | Yes | `NULL` | Submission timestamp |
| `media_keys` | jsonb | Yes | `NULL` | Proof media object keys |
| `notes` | text | Yes | `NULL` | Adopter notes |

---

## Shelter Module

### shelter_facilities

Shelter facility definitions.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `name` | varchar(255) | No | - | Unique facility name |
| `address` | text | No | - | Full address |
| `phone` | varchar(32) | No | - | Contact phone |
| `latitude` | numeric(9,6) | Yes | `NULL` | GPS latitude |
| `longitude` | numeric(9,6) | Yes | `NULL` | GPS longitude |
| `total_capacity` | integer | No | `50` | Maximum capacity |
| `status` | varchar(32) | No | `active` | `active`, `inactive`, `maintenance` |
| `facility_type` | varchar(32) | No | `shelter` | `shelter`, `clinic`, `foster_home`, `partner` |

---

### shelter_sections

Sections within a facility.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `facility_id` | UUID | No | - | FK to `shelter_facilities.id` (CASCADE) |
| `name` | varchar(128) | No | - | Section name |
| `section_type` | varchar(32) | Yes | `general` | Section type enum |
| `capacity` | integer | No | `10` | Section capacity |

---

### kennels

Individual kennels within sections.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `section_id` | UUID | No | - | FK to `shelter_sections.id` (CASCADE) |
| `identifier` | varchar(64) | No | - | Kennel identifier (e.g., K-08) |
| `capacity` | integer | No | `1` | Kennel capacity |
| `sanitation_state` | varchar(32) | No | `clean` | Sanitation status |

---

### facility_transfers

Inter-facility dog transfers.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `from_facility_id` | UUID | No | - | FK to `shelter_facilities.id` (CASCADE) |
| `to_facility_id` | UUID | No | - | FK to `shelter_facilities.id` (CASCADE) |
| `transferred_by` | UUID | No | - | FK to `users.id` (CASCADE) |
| `status` | varchar(32) | No | `pending` | `pending`, `completed`, `cancelled` |
| `notes` | text | Yes | `NULL` | Transfer notes |
| `sender_confirmed_at` | timestamptz | Yes | `NULL` | Sender confirmation timestamp |
| `sender_confirmed_by` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |
| `receiver_confirmed_at` | timestamptz | Yes | `NULL` | Receiver confirmation timestamp |
| `receiver_confirmed_by` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |

---

### daily_care_logs

Daily care operational records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `dog_id` | UUID | No | - | FK to `dog_profiles.id` (CASCADE) |
| `logged_by` | UUID | No | - | FK to `users.id` (CASCADE) |
| `feed_time` | timestamptz | No | - | Feeding timestamp |
| `dietary_requirements` | text | Yes | `NULL` | Diet notes |
| `exercise_hours` | numeric(4,2) | No | `0.0` | Exercise duration |
| `behavioral_enrichment` | text | Yes | `NULL` | Enrichment activities |

---

### kennel_cleaning_logs

Kennel cleaning rotation records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `kennel_id` | UUID | No | - | FK to `kennels.id` (CASCADE) |
| `cleaned_by` | UUID | No | - | FK to `users.id` (CASCADE) |
| `cleaned_at` | timestamptz | No | - | Cleaning timestamp |
| `sanitation_state_after` | varchar(32) | No | `clean` | Post-cleaning state |
| `cleaning_method` | varchar(64) | Yes | `NULL` | Cleaning method |
| `notes` | text | Yes | `NULL` | Cleaning notes |

---

## Fleet Module

### vehicles

Fleet vehicle records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `deleted_at` | timestamptz | Yes | `NULL` | Soft delete timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `make_model` | varchar(255) | No | - | Vehicle make and model |
| `license_plate` | varchar(64) | No | - | Unique license plate |
| `vehicle_type` | varchar(32) | Yes | `rescue_van` | Vehicle type enum |
| `status` | varchar(32) | No | `active` | `active`, `in_maintenance`, `out_of_service` |
| `mileage` | integer | No | `0` | Current mileage |
| `primary_driver_id` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |
| `insurance_provider` | varchar(255) | Yes | `NULL` | Insurance company |
| `insurance_policy_number` | varchar(128) | Yes | `NULL` | Policy number |
| `insurance_expiry_date` | date | Yes | `NULL` | Policy expiration |
| `insurance_contact_phone` | varchar(32) | Yes | `NULL` | Insurance contact |

---

### fleet_maintenances

Vehicle maintenance records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `vehicle_id` | UUID | No | - | FK to `vehicles.id` (CASCADE) |
| `service_date` | date | No | - | Service date |
| `description` | text | No | - | Service description |
| `cost` | numeric(10,2) | No | `0.0` | Service cost |
| `next_due_date` | date | Yes | `NULL` | Next service due |

---

### equipment_checkouts

Equipment checkout and return records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `equipment_name` | varchar(255) | No | - | Equipment name |
| `assigned_to_agent_id` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |
| `assigned_to_vehicle_id` | UUID | Yes | `NULL` | FK to `vehicles.id` (SET NULL) |
| `rescue_dispatch_id` | UUID | Yes | `NULL` | FK to `rescue_dispatches.id` (SET NULL) |
| `checked_out_at` | timestamptz | No | - | Checkout timestamp |
| `expected_return_at` | timestamptz | Yes | `NULL` | Expected return |
| `returned_at` | timestamptz | Yes | `NULL` | Actual return timestamp |
| `notes` | text | Yes | `NULL` | Checkout notes |

---

### fuel_logs

Vehicle fuel fill-up records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `created_at` | timestamptz | No | `now()` | Record creation timestamp |
| `updated_at` | timestamptz | No | `now()` | Last update timestamp |
| `created_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `updated_by` | UUID | Yes | `NULL` | FK to `users.id` |
| `vehicle_id` | UUID | No | - | FK to `vehicles.id` (CASCADE) |
| `filled_by_id` | UUID | Yes | `NULL` | FK to `users.id` (SET NULL) |
| `fuel_type` | varchar(32) | No | - | Fuel type |
| `volume_litres` | numeric(8,2) | No | - | Volume in litres |
| `cost` | numeric(10,2) | No | - | Total cost |
| `mileage_at_fill` | integer | No | - | Odometer reading |
| `vendor` | varchar(255) | Yes | `NULL` | Gas station/vendor |
| `receipt_url` | varchar(512) | Yes | `NULL` | Receipt image URL |
| `notes` | text | Yes | `NULL` | Additional notes |
| `filled_at` | timestamptz | No | - | Fill-up timestamp |
