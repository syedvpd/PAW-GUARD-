# Medical Module API

## Overview

The Medical module manages clinical examinations, treatments, vaccinations, prescriptions, medication administrations, vaccine protocols, and adoption clearance. All records are linked to a dog profile and the attending veterinarian.

**Prefix:** `/api/v1/medical`

---

## Endpoints

### Clinical Exams

#### Create Clinical Exam

**`POST /medical/exams`**

Logs a clinical examination. Requires `medical:create` permission.

**Request Body:**

```json
{
  "dog_id": "dog-uuid",
  "body_condition_score": 5,
  "dental_health": "Mild tartar buildup",
  "ocular_aural_notes": "Clear, no discharge.",
  "coat_condition": "Slightly matted, otherwise healthy",
  "visible_injuries": "Small laceration on left hind leg.",
  "triage_diagnosis": "Stable, mild dehydration"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dog_id` | UUID | Yes | Dog being examined |
| `body_condition_score` | integer | Yes | 1-9 scale (1=emaciated, 9=obese) |
| `triage_diagnosis` | string | Yes | Primary diagnosis |
| `dental_health` | string | No | Dental assessment |
| `ocular_aural_notes` | string | No | Eye/ear assessment |
| `coat_condition` | string | No | Coat/skin assessment |
| `visible_injuries` | string | No | External injuries |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "exam-uuid",
    "dog_id": "dog-uuid",
    "vet_id": "vet-uuid",
    "exam_date": "2026-08-18T10:30:00Z",
    "body_condition_score": 5,
    "triage_diagnosis": "Stable, mild dehydration",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Clinical examination logged successfully."
}
```

---

### Medical Treatments

#### Record Treatment

**`POST /medical/treatments`**

Records a medical treatment or surgery. Requires `medical:create` permission.

**Request Body:**

```json
{
  "dog_id": "dog-uuid",
  "treatment_type": "Spay/Neuter Surgery",
  "description": "Routine spay procedure, no complications.",
  "anesthesia_log": "Isoflurane, 45 minutes, stable vitals.",
  "post_op_notes": "Recovering well, monitor incision site.",
  "inventory_consumptions": [
    {
      "item_id": "item-uuid",
      "quantity": 2.0
    }
  ]
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "treatment-uuid",
    "dog_id": "dog-uuid",
    "vet_id": "vet-uuid",
    "treatment_date": "2026-08-18T10:30:00Z",
    "treatment_type": "Spay/Neuter Surgery",
    "description": "Routine spay procedure, no complications.",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Medical treatment / surgery logged successfully."
}
```

---

### Vaccinations

#### Record Vaccination

**`POST /medical/vaccinations`**

Records a vaccination. Requires `medical:create` permission.

**Request Body:**

```json
{
  "dog_id": "dog-uuid",
  "vaccine_name": "Rabies",
  "next_due_at": "2027-07-22T00:00:00Z",
  "lot_number": "LOT-48213"
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "vacc-uuid",
    "dog_id": "dog-uuid",
    "administered_by": "vet-uuid",
    "vaccine_name": "Rabies",
    "administered_at": "2026-08-18T10:30:00Z",
    "next_due_at": "2027-07-22T00:00:00Z",
    "lot_number": "LOT-48213",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Vaccination details logged successfully."
}
```

---

### Prescriptions

#### Create Prescription

**`POST /medical/prescriptions`**

Creates a medication prescription. Requires `medical:create` permission.

**Request Body:**

```json
{
  "dog_id": "dog-uuid",
  "drug_name": "Amoxicillin",
  "dosage": "250mg twice daily",
  "route": "Oral",
  "start_at": "2026-07-22T08:00:00Z",
  "end_at": "2026-07-29T08:00:00Z",
  "inventory_consumptions": [
    {
      "item_id": "item-uuid",
      "quantity": 1.0
    }
  ]
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "rx-uuid",
    "dog_id": "dog-uuid",
    "vet_id": "vet-uuid",
    "drug_name": "Amoxicillin",
    "dosage": "250mg twice daily",
    "route": "Oral",
    "start_at": "2026-07-22T08:00:00Z",
    "end_at": "2026-07-29T08:00:00Z",
    "is_active": true,
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Medication prescription generated successfully."
}
```

#### Update Prescription

**`PUT /medical/prescriptions/{prescription_id}`**

Updates a prescription. Requires `medical:update` permission.

**Request Body:** All fields optional except the prescription ID.

#### Update Prescription Status

**`PATCH /medical/prescriptions/{prescription_id}/status`**

Toggles a prescription active/inactive. Requires `medical:update` permission.

**Request Body:**

```json
{
  "is_active": false
}
```

---

### Medication Administration

#### Log Administration

**`POST /medical/administrations`**

Logs a medication administration sign-off. Requires `medical:update` permission.

**Request Body:**

```json
{
  "prescription_id": "rx-uuid",
  "dog_id": "dog-uuid",
  "medication_name": "Amoxicillin",
  "dosage": "5ml",
  "route": "Oral",
  "administered_at": "2026-07-29T10:00:00Z",
  "notes": "Given with food, tolerated well."
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "admin-uuid",
    "prescription_id": "rx-uuid",
    "dog_id": "dog-uuid",
    "medication_name": "Amoxicillin",
    "dosage": "5ml",
    "route": "Oral",
    "administered_at": "2026-07-29T10:00:00Z",
    "administered_by_id": "nurse-uuid",
    "notes": "Given with food, tolerated well.",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Medication administration sign-off logged successfully."
}
```

#### Get Prescription Administrations

**`GET /medical/prescriptions/{prescription_id}/administrations`**

Lists all administrations for a prescription. Requires `medical:read` permission.

#### Get Dog Administrations

**`GET /medical/dogs/{dog_id}/administrations`**

Lists all administrations for a dog. Requires `medical:read` permission.

---

### Adoption Clearance

#### Authorize Clearance

**`POST /medical/clearance/{dog_id}`**

Authorizes adoption medical clearance. Requires `medical:clearance` permission.

**Request Body:**

```json
{
  "clearance_type": "adoption_surgery",
  "status": "approved",
  "decision_notes": "Healthy, cleared for adoption.",
  "expires_at": "2026-08-03T00:00:00Z"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `clearance_type` | string | No | Default: `adoption_surgery` |
| `status` | string | Yes | `approved`, `denied`, `pending` |
| `decision_notes` | string | No | Rationale |
| `expires_at` | datetime | No | Clearance expiration |

**Response:**

```json
{
  "success": true,
  "data": true,
  "message": "Adoption medical clearance granted successfully."
}
```

#### Get Dog Clearances

**`GET /medical/clearances/dogs/{dog_id}`**

Lists all clearances for a dog. Requires `medical:read` permission.

---

### Vaccine Protocols

#### Create Protocol

**`POST /medical/vaccine-protocols`**

Creates a vaccine protocol. Requires `medical:update` permission.

**Request Body:**

```json
{
  "name": "Rabies",
  "default_interval_days": 365,
  "is_required": true
}
```

#### List Protocols

**`GET /medical/vaccine-protocols`**

Lists all vaccine protocols. Requires `medical:read` permission.

---

### Medical History

**`GET /medical/dogs/{dog_id}/history`**

Returns the complete medical history for a dog. Requires `medical:read` permission.

**Response:**

```json
{
  "success": true,
  "data": {
    "exams": [...],
    "treatments": [...],
    "vaccinations": [...],
    "prescriptions": [...]
  }
}
```

---

### List Endpoints

All list endpoints support pagination and sorting.

| Endpoint | Description | Permission |
|----------|-------------|------------|
| `GET /medical/exams` | List clinical exams | `medical:read` |
| `GET /medical/treatments` | List treatments | `medical:read` |
| `GET /medical/vaccinations` | List vaccinations | `medical:read` |
| `GET /medical/prescriptions` | List prescriptions | `medical:read` |

**Common Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |
| `search` | string | Full-text search (varies by entity) |
| `dog_id` | UUID | Filter by dog |
| `vet_id` | UUID | Filter by veterinarian |
| `sort_by` | string | Sort field (default: `created_at`) |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

---

### Soft Delete

**`DELETE /medical/{entity_type}/{entity_id}`**

Soft-deletes a medical record. Requires `medical:delete` permission.

**Entity Types:** `exams`, `treatments`, `vaccinations`, `prescriptions`

**Response:**

```json
{
  "success": true,
  "message": "Exam deleted successfully."
}
```

---

### Bulk Operations

**`POST /medical/bulk/prescriptions/status`**

Bulk updates prescription status. Requires `medical:update` permission.

**Request Body:**

```json
{
  "ids": ["rx-uuid-1", "rx-uuid-2"],
  "status": "active"
}
```

**`POST /medical/bulk/delete`**

Bulk soft-deletes prescriptions. Requires `medical:delete` permission.

**Request Body:**

```json
{
  "ids": ["rx-uuid-1", "rx-uuid-2"]
}
```
