# Adoption Module API

## Overview

The Adoption module manages the complete adoption lifecycle from application submission through vetting, home inspection, approval, and post-adoption follow-ups. It includes scoring, nearby shelter lookup, and agreement generation.

**Prefix:** `/api/v1/adoptions`

---

## Endpoints

### Find Nearby Shelters

**`GET /adoptions/nearby-shelters`**

Returns shelters within a radius of the user's location, sorted by distance, with their adoptable dogs.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `latitude` | float | Yes | Search center latitude (-90 to 90) |
| `longitude` | float | Yes | Search center longitude (-180 to 180) |
| `radius` | float | No | Search radius in km (default: 5.0, max: 100) |

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": "facility-uuid",
      "name": "Central Shelter Alpha",
      "address": "45 Rescue Road, Sector 4",
      "phone": "+1-555-0111",
      "latitude": 28.6139,
      "longitude": 77.2090,
      "facility_type": "shelter",
      "distance_km": 2.4,
      "adoptable_dogs": [
        {
          "id": "dog-uuid",
          "registration_number": "PG-2026-001",
          "name": "Barnaby",
          "breed": "Indie Mix",
          "gender": "male",
          "is_spayed_neutered": false,
          "estimated_age": "2 years",
          "age_months": 24,
          "weight": 16.4,
          "color": "Tan/White",
          "temperament": "friendly",
          "status": "shelter",
          "is_adoptable": true
        }
      ]
    }
  ],
  "message": "1 shelter(s) found within 5.0 km."
}
```

---

### Apply for Adoption

**`POST /adoptions`**

Submits an adoption application. Authentication required.

**Request Body:**

```json
{
  "dog_id": "dog-uuid",
  "residential_status": "owned",
  "has_landlord_approval": false,
  "has_yard_fence": true,
  "household_members_count": 3,
  "existing_pets_medical_details": "One neutered male cat, up to date on vaccinations.",
  "pet_care_experience": "Owned a Labrador for 10 years prior to this application."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dog_id` | UUID | Yes | Dog being applied for |
| `residential_status` | string | Yes | `owned` or `rented` |
| `has_landlord_approval` | boolean | No | Required if renting |
| `has_yard_fence` | boolean | No | Yard securely fenced |
| `household_members_count` | integer | No | Default: 1 |
| `existing_pets_medical_details` | string | No | Details of existing pets |
| `pet_care_experience` | string | No | Prior pet ownership experience |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "app-uuid",
    "dog_id": "dog-uuid",
    "adopter_id": "user-uuid",
    "status": "submitted",
    "residential_status": "owned",
    "has_landlord_approval": false,
    "has_yard_fence": true,
    "household_members_count": 3,
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Adoption application submitted successfully."
}
```

---

### List My Applications

**`GET /adoptions/my`**

Lists the current user's adoption applications.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |
| `search` | string | Search by notes, residential status |
| `status` | string | Filter by status |
| `sort_by` | string | Sort field (default: `created_at`) |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

**Response:** `PaginatedResponse[AdoptionApplicationResponse]`

---

### List All Applications

**`GET /adoptions`**

Lists all adoption applications. Staff with `adoption:read` permission see all; others see only their own.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |
| `search` | string | Search by notes, residential status |
| `status` | string | Filter by status |
| `dog_id` | UUID | Filter by dog |
| `adopter_id` | UUID | Filter by adopter (staff only) |
| `sort_by` | string | Sort field (default: `created_at`) |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

**Response:** `PaginatedResponse[AdoptionApplicationResponse]`

---

### Get Application

**`GET /adoptions/{app_id}`**

Returns a single adoption application. Users can view their own; staff with `adoption:read` can view any.

**Response:** `AdoptionApplicationResponse` object.

---

### Get Adoption Agreement

**`GET /adoptions/{app_id}/agreement`**

Returns a presigned download URL for the adoption agreement. Users can download their own; staff with `adoption:read` can download any.

**Response:**

```json
{
  "success": true,
  "data": {
    "download_url": "https://s3.amazonaws.com/...",
    "object_key": "documents/agreement_1a2b3c.pdf",
    "file_id": "app-uuid"
  }
}
```

---

### Update Application

**`PUT /adoptions/{app_id}`**

Updates an adoption application. Requires `adoption:process` permission.

**Request Body:**

```json
{
  "status": "home_check",
  "vetting_officer_notes": "Phone interview completed, applicant is a strong candidate.",
  "home_inspection_scheduled_at": "2026-08-15T14:00:00Z",
  "home_inspection_notes": "Yard is securely fenced, home is clean and pet-ready.",
  "adoption_agreement_url": "documents/agreement_1a2b3c.pdf"
}
```

**Response:** Updated `AdoptionApplicationResponse` object.

---

### Update Application Status

**`PATCH /adoptions/{app_id}/status`**

Updates the status of an adoption application. Requires `adoption:process` permission.

**Request Body:**

```json
{
  "status": "approved"
}
```

**Status Values:** `submitted`, `screening`, `interview`, `home_check`, `approved`, `completed`, `rejected`

**Response:** Updated `AdoptionApplicationResponse` object.

---

### Add Score

**`POST /adoptions/{app_id}/scores`**

Adds an adoption vetting score. Requires `adoption:process` permission.

**Request Body:**

```json
{
  "home_environment_score": 8,
  "pet_care_knowledge_score": 7,
  "financial_readiness_score": 9,
  "lifestyle_compatibility_score": 8,
  "recommendation": "approve",
  "notes": "Strong candidate, active lifestyle matches dog's energy."
}
```

| Field | Type | Required | Range |
|-------|------|----------|-------|
| `home_environment_score` | integer | Yes | 1-10 |
| `pet_care_knowledge_score` | integer | Yes | 1-10 |
| `financial_readiness_score` | integer | Yes | 1-10 |
| `lifestyle_compatibility_score` | integer | Yes | 1-10 |
| `recommendation` | string | Yes | `approve`, `reject`, `waitlist` |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "score-uuid",
    "application_id": "app-uuid",
    "scored_by_id": "officer-uuid",
    "home_environment_score": 8,
    "pet_care_knowledge_score": 7,
    "financial_readiness_score": 9,
    "lifestyle_compatibility_score": 8,
    "overall_score": 8.0,
    "recommendation": "approve",
    "scored_at": "2026-08-18T10:30:00Z",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Adoption score added successfully."
}
```

---

### Get Scores

**`GET /adoptions/{app_id}/scores`**

Returns all scores for an application. Users can view their own; staff with `adoption:read` can view any.

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": "score-uuid",
      "application_id": "app-uuid",
      "scored_by_id": "officer-uuid",
      "home_environment_score": 8,
      "overall_score": 8.0,
      "recommendation": "approve",
      "scored_at": "2026-08-18T10:30:00Z"
    }
  ]
}
```

---

### Delete Application

**`DELETE /adoptions/{app_id}`** or **`DELETE /adoptions/admin/adoptions/{app_id}`**

Soft-deletes an adoption application. Requires `adoption:process` permission.

**Response:**

```json
{
  "success": true,
  "message": "Adoption application deleted successfully."
}
```

---

### Follow-Up Management

#### Create Follow-Up

**`POST /adoptions/{app_id}/follow-ups`**

Creates a post-adoption follow-up milestone. Requires `adoption:process` permission.

**Request Body:**

```json
{
  "due_day": 30
}
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `due_day` | integer | 30-180 | Days after completion |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "followup-uuid",
    "adoption_application_id": "app-uuid",
    "due_day": 30,
    "due_at": "2026-09-17T10:30:00Z",
    "status": "pending",
    "submitted_at": null,
    "media_keys": null,
    "notes": null,
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Follow-up milestone created."
}
```

#### Get Follow-Ups

**`GET /adoptions/{app_id}/follow-ups`**

Returns all follow-ups for an application. Users can view their own; staff with `adoption:read` can view any.

#### Submit Follow-Up Proof

**`POST /adoptions/{app_id}/follow-ups/{follow_up_id}/proof`**

Submits proof media and notes for a follow-up check-in.

**Request Body:**

```json
{
  "media_keys": ["documents/followup_1a2b3c.jpg"],
  "notes": "Updated photos showing Buddy's progress."
}
```

**Response:** Updated `AdoptionFollowUpResponse` object.

---

### Update Adoption Fee

**`PUT /adoptions/{app_id}/fee`**

Sets the adoption fee before approval. Requires `adoption:process` permission.

**Request Body:**

```json
{
  "fee_amount": 250.00
}
```

**Response:** Updated `AdoptionApplicationResponse` object.

---

### Bulk Operations

**`POST /adoptions/bulk/status-update`**

Bulk updates application statuses. Requires `adoption:process` permission.

**Request Body:**

```json
{
  "ids": ["app-uuid-1", "app-uuid-2"],
  "status": "approved"
}
```

**`POST /adoptions/bulk/delete`**

Bulk soft-deletes applications. Requires `adoption:process` permission.

**Request Body:**

```json
{
  "ids": ["app-uuid-1", "app-uuid-2"]
}
```
