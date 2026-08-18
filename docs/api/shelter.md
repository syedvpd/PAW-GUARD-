# Shelter Module API

## Overview

The Shelter module manages facilities, sections, kennels, inter-facility transfers, daily care logs, and kennel cleaning. It provides the capacity management infrastructure for the rescue and adoption workflows.

**Prefix:** `/api/v1/shelter`

---

## Endpoints

### Facilities

#### Create Facility

**`POST /shelter/facilities`**

Creates a new shelter facility. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "name": "Central Shelter Alpha",
  "address": "45 Rescue Road, Sector 4",
  "phone": "+1-555-0111",
  "latitude": 28.6139,
  "longitude": 77.2090,
  "total_capacity": 100,
  "facility_type": "shelter"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Facility name (1-255 chars) |
| `address` | string | Yes | Full address |
| `phone` | string | Yes | Contact phone |
| `latitude` | float | No | GPS latitude (-90 to 90) |
| `longitude` | float | No | GPS longitude (-180 to 180) |
| `total_capacity` | integer | No | Default: 50 |
| `facility_type` | string | No | `shelter`, `clinic`, `foster_home`, `partner` (default: `shelter`) |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "facility-uuid",
    "name": "Central Shelter Alpha",
    "address": "45 Rescue Road, Sector 4",
    "phone": "+1-555-0111",
    "latitude": 28.6139,
    "longitude": 77.2090,
    "total_capacity": 100,
    "status": "active",
    "facility_type": "shelter",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Shelter facility created successfully."
}
```

---

#### List Facilities

**`GET /shelter/facilities`**

Lists facilities with filtering and pagination. Requires `shelter:read` permission.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |
| `search` | string | Search by name or address |
| `status` | string | Filter: `active`, `inactive`, `maintenance` |
| `facility_type` | string | Filter: `shelter`, `clinic`, `foster_home`, `partner` |
| `sort_by` | string | Sort field (default: `created_at`) |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

**Response:** `PaginatedResponse[ShelterFacilityResponse]`

---

#### Get Facility

**`GET /shelter/facilities/{facility_id}`**

Returns a single facility. Requires `shelter:read` permission.

**Response:** `ShelterFacilityResponse` object.

---

#### Update Facility

**`PUT /shelter/facilities/{facility_id}`**

Updates a facility. Requires `shelter:update` permission.

**Request Body:** Same as create, all fields optional.

**Response:** Updated `ShelterFacilityResponse` object.

---

#### Update Facility Status

**`PUT /shelter/facilities/{facility_id}/status`**

Updates facility status. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "status": "maintenance"
}
```

---

#### Delete Facility

**`DELETE /shelter/facilities/{facility_id}`**

Soft-deletes a facility. Requires `shelter:update` permission.

**Response:**

```json
{
  "success": true,
  "message": "Shelter facility deleted."
}
```

---

#### Bulk Facility Operations

**`POST /shelter/facilities/bulk/delete`**

Bulk deletes facilities. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "ids": ["facility-uuid-1", "facility-uuid-2"]
}
```

**`POST /shelter/facilities/bulk/status`**

Bulk updates facility statuses. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "ids": ["facility-uuid-1", "facility-uuid-2"],
  "status": "active"
}
```

---

### Sections

#### Create Section

**`POST /shelter/facilities/{facility_id}/sections`**

Creates a section within a facility. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "name": "Quarantine",
  "section_type": "quarantine",
  "capacity": 15
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Section name (1-128 chars) |
| `section_type` | string | No | `quarantine`, `isolation`, `surgical`, `puppy`, `general`, `adoption` |
| `capacity` | integer | No | Default: 10 |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "section-uuid",
    "facility_id": "facility-uuid",
    "name": "Quarantine",
    "section_type": "quarantine",
    "capacity": 15,
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Shelter section created successfully."
}
```

---

#### List Sections

**`GET /shelter/facilities/{facility_id}/sections`**

Lists sections within a facility. Requires `shelter:read` permission.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |
| `search` | string | Search by name |
| `section_type` | string | Filter by section type |
| `sort_by` | string | Sort field (default: `created_at`) |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

**Response:** `PaginatedResponse[ShelterSectionResponse]`

---

### Kennels

#### Create Kennel

**`POST /shelter/sections/{section_id}/kennels`**

Creates a kennel within a section. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "identifier": "K-08",
  "capacity": 2
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "kennel-uuid",
    "section_id": "section-uuid",
    "identifier": "K-08",
    "capacity": 2,
    "sanitation_state": "clean",
    "is_occupied": false,
    "occupied_by_dog_id": null,
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Kennel created successfully."
}
```

---

#### List Kennels

**`GET /shelter/sections/{section_id}/kennels`**

Lists kennels within a section with occupancy data. Requires `shelter:read` permission.

**Response:** `PaginatedResponse[KennelResponse]`

---

#### Assign Dog to Kennel

**`POST /shelter/kennels/{kennel_id}/assign/{dog_id}`** or **`PATCH /shelter/kennels/{kennel_id}/assign/{dog_id}`**

Assigns a dog to a kennel. Requires `shelter:update` permission.

**Response:**

```json
{
  "success": true,
  "data": true,
  "message": "Dog successfully assigned to kennel."
}
```

---

#### Update Kennel Sanitation

**`PUT /shelter/kennels/{kennel_id}/sanitation`**

Updates kennel sanitation status. Requires `shelter:update` permission.

**Query Parameter:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status_val` | string | `clean`, `needs_cleaning`, `disinfecting`, `out_of_service` |

**Response:** Updated `KennelResponse` object.

---

#### Log Kennel Cleaning

**`POST /shelter/kennels/{kennel_id}/cleaning-logs`**

Logs a kennel cleaning rotation. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "method": "pressure wash",
  "notes": "Full disinfection after parvo case."
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "log-uuid",
    "kennel_id": "kennel-uuid",
    "cleaned_by": "user-uuid",
    "cleaned_at": "2026-08-18T10:30:00Z",
    "sanitation_state_after": "clean",
    "cleaning_method": "pressure wash",
    "notes": "Full disinfection after parvo case.",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Kennel cleaning rotation logged successfully."
}
```

---

#### List Cleaning Logs

**`GET /shelter/kennels/{kennel_id}/cleaning-logs`**

Lists cleaning logs for a kennel. Requires `shelter:read` permission.

**Response:** `PaginatedResponse[KennelCleaningLogResponse]`

---

### Inter-Facility Transfers

#### Request Transfer

**`POST /shelter/transfers`**

Creates an inter-facility transfer request. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "dog_id": "dog-uuid",
  "from_facility_id": "facility-uuid-1",
  "to_facility_id": "facility-uuid-2",
  "notes": "Transferring for specialized surgical care."
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "transfer-uuid",
    "dog_id": "dog-uuid",
    "from_facility_id": "facility-uuid-1",
    "to_facility_id": "facility-uuid-2",
    "transferred_by": "user-uuid",
    "status": "pending",
    "notes": "Transferring for specialized surgical care.",
    "sender_confirmed_at": null,
    "receiver_confirmed_at": null,
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Inter-facility transfer request submitted successfully."
}
```

---

#### List Transfers

**`GET /shelter/transfers`**

Lists all transfers. Requires `shelter:read` permission.

---

#### Get Transfer

**`GET /shelter/transfers/{transfer_id}`**

Returns a single transfer. Requires `shelter:read` permission.

---

#### Confirm Transfer (Sender)

**`POST /shelter/transfers/{transfer_id}/confirm-sender`**

Confirms the sending facility's side. Requires `shelter:update` permission.

**Response:** Updated `FacilityTransferResponse` object.

---

#### Confirm Transfer (Receiver)

**`POST /shelter/transfers/{transfer_id}/confirm-receiver`**

Confirms the receiving facility's side. A transfer only completes once both confirmations are recorded. Requires `shelter:update` permission.

**Response:** Updated `FacilityTransferResponse` object.

---

### Daily Care Logs

#### Submit Care Log

**`POST /shelter/care-logs`**

Logs daily care operational updates. Requires `shelter:update` permission.

**Request Body:**

```json
{
  "dog_id": "dog-uuid",
  "dietary_requirements": "Grain-free diet, small portions 3x daily",
  "exercise_hours": 1.5,
  "behavioral_enrichment": "Puzzle feeder, 20 min outdoor play",
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
    "id": "log-uuid",
    "dog_id": "dog-uuid",
    "logged_by": "user-uuid",
    "feed_time": "2026-08-18T10:30:00Z",
    "dietary_requirements": "Grain-free diet, small portions 3x daily",
    "exercise_hours": 1.5,
    "behavioral_enrichment": "Puzzle feeder, 20 min outdoor play",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Daily care operational updates recorded successfully."
}
```

---

#### List Care Logs

**`GET /shelter/dogs/{dog_id}/care-logs`**

Lists care logs for a dog. Requires `shelter:read` permission.

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": "log-uuid",
      "dog_id": "dog-uuid",
      "logged_by": "user-uuid",
      "feed_time": "2026-08-18T10:30:00Z",
      "dietary_requirements": "Grain-free diet, small portions 3x daily",
      "exercise_hours": 1.5,
      "behavioral_enrichment": "Puzzle feeder, 20 min outdoor play",
      "created_at": "2026-08-18T10:30:00Z"
    }
  ]
}
```
