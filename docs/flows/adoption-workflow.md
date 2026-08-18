# Adoption Workflow

## Overview

The adoption workflow is a six-phase pipeline that tracks applications from submission through completion. The implementation is in `src/pawguard/modules/adoption/service.py`.

## State Machine

```
SUBMITTED --> SCREENING --> INTERVIEW --> HOME_CHECK --> APPROVED --> COMPLETED
    |                                                            |
    +--> REJECTED                                                +--> REJECTED
```

### Status Definitions

| Status | Description |
|--------|-------------|
| `submitted` | Application received from adopter |
| `screening` | Initial application review |
| `interview` | In-person or virtual interview |
| `home_check` | Home inspection scheduled/completed |
| `approved` | Application approved, adoption agreement generated |
| `completed` | Dog transferred to adopter |
| `rejected` | Application rejected at any stage |

## Application Fields

### Residential Information
- `residential_status`: owned, rented
- `has_landlord_approval`: Boolean (required for renters)
- `has_yard_fence`: Boolean
- `household_members_count`: Integer

### Pet Experience
- `existing_pets_medical_details`: Description of current pets
- `pet_care_experience`: Previous pet care experience

### Vetting Data
- `vetting_officer_notes`: Coordinator notes during screening
- `home_inspection_scheduled_at`: Scheduled inspection datetime
- `home_inspection_notes`: Inspection findings
- `adoption_agreement_url`: Generated agreement PDF
- `completed_at`: Completion timestamp
- `fee_amount`: Adoption fee

## Adoption Scoring

### Score Categories
- `home_environment_score`: Assessment of living situation
- `pet_care_knowledge_score`: Knowledge of pet care
- `financial_readiness_score`: Financial capability
- `lifestyle_compatibility_score`: Lifestyle fit
- `overall_score`: Weighted average
- `recommendation`: approve, conditional, reject

### Scoring Actor
- `scored_by_id`: Staff member who scored the application

## Follow-Up System

### Scheduled Check-Ins
- 30 days after completion
- 90 days after completion
- 180 days after completion

### Follow-Up Status
- `pending`: Scheduled, awaiting submission
- `submitted`: Adopter submitted proof
- `overdue`: Past due date, not submitted

### Follow-Up Data
- `media_keys`: Photos/videos from adopter
- `notes`: Adopter notes

## Workflow Steps

### 1. Submit Application

**Actor**: Public user (authenticated)

**Endpoint**: `POST /adoption`

**Data Required**:
- Dog ID
- Residential status
- Landlord approval (if rented)
- Yard fence status
- Household members count
- Pet care experience

**Side Effects**:
- Application created with `SUBMITTED` status
- Audit event (`adoption_submitted`)

### 2. Screen Application

**Actor**: Adoption coordinator

**Endpoint**: `PATCH /adoption/{id}/status`

**Transition**: `SUBMITTED` -> `SCREENING`

**Data Captured**:
- Vetting officer notes

### 3. Interview

**Actor**: Adoption coordinator

**Transition**: `SCREENING` -> `INTERVIEW`

### 4. Home Check

**Actor**: Adoption coordinator

**Endpoint**: `PATCH /adoption/{id}/status`

**Transition**: `INTERVIEW` -> `HOME_CHECK`

**Data Captured**:
- Home inspection scheduled datetime
- Home inspection notes

### 5. Score Application

**Actor**: Adoption coordinator

**Endpoint**: `POST /adoption/{id}/score`

**Data Required**:
- Home environment score (1-10)
- Pet care knowledge score (1-10)
- Financial readiness score (1-10)
- Lifestyle compatibility score (1-10)
- Recommendation (approve/conditional/reject)
- Notes

### 6. Approve Application

**Actor**: Adoption coordinator

**Endpoint**: `PATCH /adoption/{id}/status`

**Transition**: `HOME_CHECK` -> `APPROVED`

**Side Effects**:
- Adoption agreement generated
- Audit event (`adoption_agreement_generated`)

### 7. Complete Adoption

**Actor**: Adoption coordinator

**Endpoint**: `PATCH /adoption/{id}/status`

**Transition**: `APPROVED` -> `COMPLETED`

**Side Effects**:
- Dog status updated to `ADOPTED`
- Follow-up schedule created (30/90/180 days)
- Audit event (`adoption_status_changed`)

### 8. Submit Follow-Up

**Actor**: Adopter

**Endpoint**: `POST /adoption/{id}/follow-up/{follow_up_id}`

**Data Required**:
- Media (photos/videos)
- Notes

**Side Effects**:
- Follow-up status updated to `SUBMITTED`
- Audit event recorded

## Bulk Operations

### Bulk Status Update

**Endpoint**: `POST /adoption/bulk/status`

**Valid Transitions**:
- `SUBMITTED` -> `SCREENING`
- `SCREENING` -> `INTERVIEW`
- `INTERVIEW` -> `HOME_CHECK`
- `HOME_CHECK` -> `APPROVED`
- `APPROVED` -> `COMPLETED`

### Bulk Soft Delete

**Endpoint**: `POST /adoption/bulk/delete`

## Security

- Adopters can only view their own applications
- Coordinators can view all applications
- Status transitions enforced by service layer
- Audit trail for all state changes
