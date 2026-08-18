# Dog Management API

## Overview

The Dog Management module handles dog profile registration, lifecycle tracking, weight history, QR code generation, and Safety Tag provisioning. Public endpoints expose only adoptable dogs for the adoption directory.

**Prefix:** `/api/v1/dogs`

---

## Endpoints

### Register Dog

**`POST /dogs`**

Registers a new dog profile. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "rescue_case_id": "rescue-uuid",
  "microchip_id": "985141002345678",
  "name": "Barnaby",
  "breed": "Indie Mix",
  "breed_classification": "pure",
  "gender": "male",
  "is_spayed_neutered": false,
  "estimated_age": "2 years",
  "age_months": 24,
  "weight": 16.4,
  "color": "Tan/White",
  "temperament": "friendly",
  "ear_shape": "floppy",
  "tail_type": "curled",
  "distinctive_markers": "White patch on chest, notched left ear",
  "shelter_facility_id": "facility-uuid",
  "section_id": "section-uuid",
  "kennel_id": "kennel-uuid",
  "is_adoptable": false,
  "is_quarantine_passed": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Dog's name (1-255 chars) |
| `breed` | string | No | Breed name (default: `indie_mix`) |
| `breed_classification` | string | No | `pure`, `mix`, `unknown` |
| `gender` | string | No | `male`, `female`, `unknown` |
| `estimated_age` | string | No | Human-readable age (e.g., "2 years") |
| `age_months` | integer | No | Numeric age in months (0-600) |
| `weight` | float | No | Weight in kg |
| `temperament` | string | No | See temperament values below |
| `is_adoptable` | boolean | No | Default: `false` |

**Temperament Values:**
- `friendly` - Friendly
- `timid_fearful` - Timid/Fearful
- `aggressive` - Aggressive
- `high_energy` - High Energy
- `pack_compatible` - Pack Compatible
- `cat_child_safe` - Cat/Child Safe
- `unknown` - Unknown

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "dog-uuid",
    "registration_number": "PG-2026-001",
    "name": "Barnaby",
    "breed": "Indie Mix",
    "breed_classification": "pure",
    "gender": "male",
    "status": "rescued",
    "is_adoptable": false,
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Dog profile registered successfully."
}
```

---

### List Dogs

**`GET /dogs`**

Lists dog profiles with filtering and pagination. Public users see only adoptable dogs; staff see all dogs.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |
| `search` | string | Search by name, breed, registration number |
| `status` | string | Filter by status: `rescued`, `clinic`, `shelter`, `fostered`, `adopted` |
| `is_adoptable` | boolean | Filter by adoptable status |
| `breed` | string | Filter by breed |
| `breed_classification` | string | `pure`, `mix`, `unknown` |
| `gender` | string | `male`, `female`, `unknown` |
| `temperament` | string | Filter by temperament |
| `min_age_months` | integer | Minimum age in months |
| `max_age_months` | integer | Maximum age in months |
| `min_weight` | float | Minimum weight in kg |
| `max_weight` | float | Maximum weight in kg |
| `location` | string | Free-text match on shelter facility name/address |
| `sort_by` | string | Sort field (default: `created_at`) |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

**Response:** `PaginatedResponse[DogProfileResponse]`

**Public View Behavior:** Non-staff callers receive only adoptable dogs with internal identifiers (microchip_id, rescue_case_id, shelter_facility_id, section_id, kennel_id, foster_home_id) set to `null`.

---

### Get Dog

**`GET /dogs/{dog_id}`**

Returns a single dog profile. Staff can view any dog; public users can only view adoptable dogs.

**Response:** `DogProfileResponse` object.

---

### Get Dog Timeline

**`GET /dogs/{dog_id}/timeline`**

Returns the lifecycle activity stream for a dog. Requires `shelter:read` permission.

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": "log-uuid",
      "dog_id": "dog-uuid",
      "actor_id": "user-uuid",
      "event_type": "registered",
      "message": "Dog profile registered",
      "event_metadata": null,
      "created_at": "2026-08-18T10:30:00Z"
    }
  ],
  "message": "1 activity event(s)."
}
```

**Event Types:** `registered`, `updated`, `status_changed`, `deleted`, `weight_recorded`, `bulk_status_updated`, `bulk_deleted`

---

### Public QR Scan

**`GET /dogs/{dog_id}/public-scan`**

Returns privacy-safe dog status for QR code scanning. No authentication required.

**Rate Limit:** 20 requests per minute

**Response:**

```json
{
  "success": true,
  "data": {
    "name": "Barnaby",
    "breed": "Indie Mix",
    "breed_classification": "pure",
    "estimated_age": "2 years",
    "gender": "male",
    "weight_kg": 16.4,
    "temperament": "friendly",
    "color": "Tan/White",
    "photo_gallery_urls": ["https://cdn.example.com/dogs/barnaby.jpg"],
    "current_status": "adopted",
    "is_adoptable": false,
    "registration_number": "PG-2026-001",
    "adopter_name": "Jane Doe",
    "adopter_phone": "+1-555-0100"
  }
}
```

---

### Generate QR Image

**`GET /dogs/{dog_id}/qr-image`**

Generates a PNG QR code image for the dog profile. Requires `shelter:update` permission.

**Response:** Binary PNG image with `Content-Disposition: inline; filename="PG-2026-001.png"`

---

### Record Weight

**`POST /dogs/{dog_id}/weight`**

Appends a weight measurement to a dog's history. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "weight": 16.4,
  "measured_at": "2026-08-18T10:30:00Z",
  "notes": "Post-surgery weigh-in"
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "log-uuid",
    "dog_id": "dog-uuid",
    "measured_by": "user-uuid",
    "weight": 16.4,
    "measured_at": "2026-08-18T10:30:00Z",
    "notes": "Post-surgery weigh-in",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Weight recorded successfully."
}
```

---

### Get Weight History

**`GET /dogs/{dog_id}/weights`**

Returns chronological weight history. Requires `shelter:read` permission.

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": "log-uuid",
      "dog_id": "dog-uuid",
      "measured_by": "user-uuid",
      "weight": 16.4,
      "measured_at": "2026-08-18T10:30:00Z",
      "notes": "Post-surgery weigh-in",
      "created_at": "2026-08-18T10:30:00Z"
    }
  ],
  "message": "1 weight record(s)."
}
```

---

### Update Dog

**`PUT /dogs/{dog_id}`**

Updates a dog profile. Requires `shelter:update` permission.

**Request Body:** Same as registration, all fields optional.

**Response:** Updated `DogProfileResponse` object.

---

### Update Dog Status

**`PATCH /dogs/{dog_id}/status`** or **`PATCH /dogs/admin/dogs/{dog_id}/status`**

Updates the status of a dog. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "status": "shelter"
}
```

**Status Values:** `rescued`, `clinic`, `shelter`, `fostered`, `adopted`

**Response:** Updated `DogProfileResponse` object.

---

### Soft Delete Dog

**`DELETE /dogs/{dog_id}`**

Soft-deletes a dog profile. Requires `shelter:update` permission.

**Response:**

```json
{
  "success": true,
  "message": "Dog profile deleted successfully."
}
```

---

### Bulk Operations

**`POST /dogs/bulk/status-update`**

Bulk updates dog statuses. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "ids": ["dog-uuid-1", "dog-uuid-2"],
  "status": "shelter"
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "message": "2 dog(s) status updated.",
    "updated_count": 2
  }
}
```

**`POST /dogs/bulk/delete`**

Bulk soft-deletes dogs. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "ids": ["dog-uuid-1", "dog-uuid-2"]
}
```

---

### Safety Tag Management

#### Provision Safety Tag

**`POST /dogs/{dog_id}/safety-tag`**

Provisions a permanent Safety Tag for a dog. Requires `safety_tag:manage` permission.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `force_reissue` | boolean | false | Revoke existing active tag and provision replacement |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "tag-uuid",
    "dog_id": "dog-uuid",
    "pet_id": null,
    "token_prefix": "PGT-",
    "is_active": true,
    "last_scanned_at": null,
    "scan_count": 0,
    "created_at": "2026-08-18T10:30:00Z",
    "updated_at": "2026-08-18T10:30:00Z",
    "raw_token": "raw-token-value-shown-once"
  },
  "message": "Safety Tag provisioned successfully."
}
```

**Note:** The `raw_token` is only returned once at provisioning time.

#### Get Safety Tag

**`GET /dogs/{dog_id}/safety-tag`**

Returns active Safety Tag metadata. Requires `safety_tag:manage` permission.

**Response:** `DogSafetyTagResponse` object (without `raw_token`).

#### Deactivate Safety Tag

**`DELETE /dogs/{dog_id}/safety-tag`**

Deactivates/revokes an active Safety Tag. Requires `safety_tag:manage` permission.

**Response:**

```json
{
  "success": true,
  "message": "Safety Tag deactivated successfully."
}
```
