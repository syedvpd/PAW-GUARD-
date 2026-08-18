# Medical Clearance Workflow

## Overview

The medical clearance workflow manages veterinary decisions for adoption readiness, surgical approval, and health status. The implementation is in `src/pawguard/modules/medical/service.py`.

## Data Models

### MedicalClearance
- `dog_id`: Dog being assessed
- `authorized_by_id`: Veterinarian making the decision
- `clearance_type`: Type of clearance (adoption_surgery, pre_adoption_medical, surgical_review, etc.)
- `status`: pending, approved, denied
- `decision_notes`: Rationale for decision
- `authorized_at`: Decision timestamp
- `expires_at`: Clearance expiration (optional)

### ClinicalExam
- `dog_id`: Dog examined
- `vet_id`: Veterinarian performing exam
- `exam_date`: Examination date
- `body_condition_score`: 1-9 scale assessment
- `dental_health`: Dental condition notes
- `ocular_aural_notes`: Eye/ear condition
- `coat_condition`: Coat condition
- `visible_injuries`: Injury description
- `triage_diagnosis`: Primary diagnosis

### MedicalTreatment
- `dog_id`: Dog being treated
- `vet_id`: Veterinarian treating
- `treatment_date`: Treatment date
- `treatment_type`: surgery, therapy, dressing, etc.
- `description`: Treatment description
- `anesthesia_log`: Anesthesia details (for surgeries)
- `post_op_notes`: Post-operative care notes

### VaccinationRecord
- `dog_id`: Dog vaccinated
- `administered_by`: Staff member administering
- `vaccine_name`: Vaccine type (DHPP, Rabies, Dewormer, etc.)
- `administered_at`: Administration timestamp
- `next_due_at`: Next dose due date
- `lot_number`: Vaccine lot number

### Prescription
- `dog_id`: Dog prescribed
- `vet_id`: Prescribing veterinarian
- `drug_name`: Medication name
- `dosage`: Dosage (e.g., "5ml", "1 tablet")
- `route`: Oral, IV, IM, etc.
- `start_at`: Start date
- `end_at`: End date
- `is_active`: Currently active

### MedicationAdministrationLog
- `prescription_id`: Associated prescription (nullable)
- `dog_id`: Dog receiving medication
- `medication_name`: Medication name
- `dosage`: Dosage
- `route`: Administration route
- `administered_at`: Administration timestamp
- `administered_by_id`: Staff member administering
- `notes`: Administration notes

### VaccineProtocol
- `name`: Protocol name
- `default_interval_days`: Days between doses
- `is_required`: Mandatory protocol

## Workflow Steps

### 1. Intake Examination

**Actor**: Veterinarian

**Endpoint**: `POST /medical/exams`

**Data Captured**:
- Body condition score (1-9)
- Dental health
- Ocular/aural notes
- Coat condition
- Visible injuries
- Triage diagnosis

**Side Effects**:
- Clinical exam record created
- Audit event (`medical_record_created`)

### 2. Record Treatment

**Actor**: Veterinarian

**Endpoint**: `POST /medical/treatments`

**Data Captured**:
- Treatment type (surgery, therapy, dressing)
- Description
- Anesthesia log (if surgery)
- Post-op notes

### 3. Administer Vaccination

**Actor**: Veterinarian or nurse

**Endpoint**: `POST /medical/vaccinations`

**Data Captured**:
- Vaccine name
- Administration timestamp
- Next due date
- Lot number

**Side Effects**:
- Vaccination record created
- Audit event (`vaccination_recorded`)

### 4. Create Prescription

**Actor**: Veterinarian

**Endpoint**: `POST /medical/prescriptions`

**Data Captured**:
- Drug name
- Dosage
- Route
- Start/end dates

### 5. Log Medication Administration

**Actor**: Nurse or vet tech

**Endpoint**: `POST /medical/administrations`

**Data Captured**:
- Prescription ID (if applicable)
- Medication name
- Dosage
- Route
- Notes

### 6. Issue Medical Clearance

**Actor**: Veterinarian

**Endpoint**: `POST /medical/clearances`

**Data Captured**:
- Clearance type
- Status (approved/denied/pending)
- Decision notes
- Expiration date (optional)

**Side Effects**:
- Dog `is_adoptable` flag updated if adoption clearance
- Audit event (`medical_record_created`)

## Clearance Types

| Type | Description |
|------|-------------|
| `adoption_surgery` | Clearance for pre-adoption surgery (spay/neuter) |
| `pre_adoption_medical` | Medical clearance for adoption |
| `surgical_review` | Post-surgical assessment |

## Body Condition Score

| Score | Description |
|-------|-------------|
| 1 | Emaciated |
| 2 | Very thin |
| 3 | Thin |
| 4 | Underweight |
| 5 | Ideal |
| 6 | Overweight |
| 7 | Heavy |
| 8 | Obese |
| 9 | Morbidly obese |

## Security

- Only veterinarians can issue medical clearances
- Only veterinarians can create prescriptions
- Nurses/techs can log medication administrations
- All actions audit logged with actor information
- Medical records soft-deleted (no hard deletes)
