# Rescue Module API

## Overview

The Rescue module manages the complete emergency rescue lifecycle from incident reporting through dispatch, field operations, and shelter admission. It supports both authenticated staff workflows and anonymous public reporting.

**Prefix:** `/api/v1/rescue` (authenticated), `/api/v1/public/rescue` (anonymous)

---

## Endpoints

### Report Incident (Authenticated)

**`POST /rescue/report`**

Reports an emergency incident. Requires `rescue:create` permission.

**Rate Limit:** 5 requests per minute

**Request Body:**

```json
{
  "reporter_name": "John Smith",
  "reporter_phone": "+1-555-0123",
  "reporter_alternate_phone": "+1-555-0199",
  "reporter_email": "john.smith@example.com",
  "is_anonymous": false,
  "location_address": "123 Main Street, Sector 4",
  "location_landmark": "Near Central Park entrance",
  "latitude": 17.4482,
  "longitude": 78.3741,
  "animal_count": 1,
  "physical_condition": "fractured_injured",
  "behavioral_indicators": "Timid, appears malnourished",
  "severity": "high",
  "is_urgent": false,
  "media_evidence": ["rescue/2026/08/barnaby_1.jpg"],
  "environmental_factors": "Heavy rain, flooding on Sector 4 roads",
  "reporter_notes": "Dog appears friendly but scared"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reporter_name` | string | Yes | Name of the person reporting |
| `reporter_phone` | string | Yes | Contact phone number |
| `reporter_alternate_phone` | string | No | Alternate phone number |
| `reporter_email` | string | No | Contact email |
| `is_anonymous` | boolean | No | Default: `false` |
| `location_address` | string | Yes | Full address of the incident |
| `location_landmark` | string | No | Nearby landmark |
| `latitude` | float | No | GPS latitude (-90 to 90) |
| `longitude` | float | No | GPS longitude (-180 to 180) |
| `animal_count` | integer | No | Default: 1 |
| `physical_condition` | string | Yes | See enum values below |
| `behavioral_indicators` | string | No | Observable behavior notes |
| `severity` | string | No | `critical`, `high`, `medium`, `low` (default) |
| `is_urgent` | boolean | No | Flag for urgent community alert |
| `media_evidence` | string[] | No | Up to 5 storage object keys |
| `environmental_factors` | string | No | Weather, terrain, hazards |
| `reporter_notes` | string | No | Additional observations |

**Physical Condition Values:**
- `critical_life_threatening` - Critical / Life Threatening
- `fractured_injured` - Fractured / Injured
- `contagious_sick` - Contagious Disease / Sick
- `malnourished` - Malnourished
- `abandoned_stray` - Abandoned / Stray
- `unknown` - Unknown

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "rescue-uuid",
    "ticket_number": "RES-2026-001",
    "reporter_name": "John Smith",
    "reporter_phone": "+1-555-0123",
    "location_address": "123 Main Street, Sector 4",
    "animal_count": 1,
    "physical_condition": "fractured_injured",
    "severity": "high",
    "status": "reported",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Emergency incident reported successfully."
}
```

---

### Report Incident (Public/Anonymous)

**`POST /public/rescue/report`**

Anonymous public emergency reporting. No authentication required.

**Rate Limit:** 5 requests per minute

**Request Body:** Same as authenticated report.

**Response:** Same as authenticated report.

---

### Request Media Upload URL

**`POST /rescue/media-upload-url`**

Generates a presigned S3 upload URL for incident photos/videos (max 50MB).

**Rate Limit:** 10 requests per minute

**Request Body:**

```json
{
  "filename": "incident_photo1.jpg",
  "mime_type": "image/jpeg",
  "file_size": 2048000
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "upload_url": "https://s3.amazonaws.com/pawguard-media/...",
    "object_key": "rescue/2026/08/incident_photo1_abc123.jpg"
  },
  "message": "Presigned upload URL generated successfully."
}
```

---

### Verify Request

**`POST /rescue/{request_id}/verify`**

Approves or rejects a rescue request. Requires `rescue:verify` permission.

**Request Body:**

```json
{
  "status": "verified",
  "rejection_rationale": null,
  "severity": "critical",
  "is_urgent": true
}
```

**Response:** `RescueRequestResponse` object.

---

### Assign Coordinator

**`POST /rescue/{request_id}/assign-coordinator`**

Assigns a coordinator to oversee a rescue case. Requires `rescue:dispatch` permission.

**Request Body:**

```json
{
  "coordinator_id": "550e8400-e29b-41d4-a716-446655440000",
  "notes": "Please prioritise this case - animal is in critical condition."
}
```

**Response:** `RescueRequestResponse` object.

---

### Dispatch Team

**`POST /rescue/{request_id}/dispatch`**

Dispatches a rescue vehicle and team. Requires `rescue:dispatch` permission.

**Request Body:**

```json
{
  "assigned_driver_id": "driver-uuid",
  "assigned_agent_ids": ["agent-uuid-1", "agent-uuid-2"],
  "vehicle_id": "RESCUE-01",
  "assigned_vehicle_id": "vehicle-uuid",
  "equipment_details": "Net gun, crate, first aid kit",
  "escalation_type": "backup_personnel",
  "escalation_notes": "Second team needed - dog is aggressive.",
  "notes": "Priority dispatch for critical case."
}
```

**Response:** `RescueRequestResponse` object.

---

### Update Dispatch

**`PATCH /rescue/dispatches/{dispatch_id}`** or **`PATCH /rescue/dispatch/{dispatch_id}`**

Updates an existing rescue dispatch. Requires `rescue:dispatch` permission.

**Request Body:**

```json
{
  "assigned_driver_id": "new-driver-uuid",
  "assigned_agent_ids": ["agent-uuid-1"],
  "status": "located",
  "failure_reason": null,
  "notes": "Updated equipment list."
}
```

**Response:** `RescueDispatchResponse` object.

---

### Delete Dispatch

**`DELETE /rescue/dispatches/{dispatch_id}`** or **`DELETE /rescue/dispatch/{dispatch_id}`**

Deletes a rescue dispatch. Requires `rescue:delete` permission.

**Response:**

```json
{
  "success": true,
  "message": "Rescue dispatch deleted successfully."
}
```

---

### Escalate Rescue

**`POST /rescue/{request_id}/escalate`**

Escalates a rescue case for additional support. Requires `rescue:update` permission.

**Request Body:**

```json
{
  "escalation_type": "vet_transport",
  "escalation_notes": "Animal needs immediate veterinary attention."
}
```

**Response:** `RescueRequestResponse` object.

---

### Status Transition Endpoints

These endpoints advance the rescue through its lifecycle. All require authentication and appropriate permissions.

| Endpoint | Permission | Status Transition | Description |
|----------|------------|-------------------|-------------|
| `POST /rescue/{request_id}/located` | `rescue:execute` | DISPATCHED -> LOCATED | Agent reached the location |
| `POST /rescue/{request_id}/secured` | `rescue:execute` | LOCATED -> RESCUED | Animal secured and in transit |
| `POST /rescue/{request_id}/admitted` | `rescue:dispatch` | RESCUED -> ADMITTED | Animal admitted to shelter |
| `POST /rescue/{request_id}/fail` | `rescue:execute` | Any -> REJECTED | Mark rescue as failed |

**Request Body for admit:**

```json
{
  "notes": "Animal admitted, initial assessment complete.",
  "photos": ["rescue/admission/photo1.jpg"]
}
```

**Request Body for fail:**

Query parameter: `failure_reason` (string)

Failure reason values:
- `animal_fled` - Animal fled the area
- `area_inaccessible` - Area inaccessible
- `false_report` - False report
- `local_intervention_blocked` - Local intervention blocked
- `other` - Other reason

---

### Accept Dispatch

**`POST /rescue/{request_id}/accept`**

Agent accepts an assigned dispatch. Requires `rescue:execute` permission.

**Response:** `RescueRequestResponse` object.

---

### Add Observation Report

**`POST /rescue/{request_id}/reports`**

Adds a field observation report. Requires `rescue:execute` permission.

**Request Body:**

```json
{
  "notes": "Animal located in abandoned building, corner is agitated.",
  "photos": ["rescue/observation/photo1.jpg"]
}
```

**Response:** `RescueRequestResponse` object.

---

### Public Status Lookup

**`GET /rescue/status`**

Looks up a rescue case status by ticket number and phone. No authentication required.

**Rate Limit:** 10 requests per minute

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticket_number` | string | Yes | Rescue ticket number |
| `phone` | string | Yes | Reporter phone number |

**Response:**

```json
{
  "success": true,
  "data": {
    "ticket_number": "RES-2026-001",
    "status": "dispatched",
    "severity": "high",
    "animal_count": 1,
    "created_at": "2026-08-18T10:30:00Z",
    "updated_at": "2026-08-18T11:00:00Z"
  }
}
```

---

### List Dispatches

**`GET /rescue/dispatches`**

Lists all rescue dispatches with pagination. Requires `rescue:read` permission.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `page_size` | integer | 20 | Items per page (max 100) |
| `sort_by` | string | `created_at` | Sort field |
| `sort_order` | string | `desc` | `asc` or `desc` |

**Response:** `PaginatedResponse[RescueDispatchResponse]`

---

### Get Rescue Request

**`GET /rescue/{request_id}`**

Returns a single rescue request with full details. Authenticated users can view; rescue agents can only view assigned cases.

**Response:** `RescueRequestResponse` object.

---

### List Rescue Requests

**`GET /rescue`**

Lists rescue requests with filtering and pagination.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |
| `search` | string | Search by ticket, reporter name, phone, or location |
| `status` | string | Filter by status |
| `severity` | string | Filter by severity |
| `urgent_only` | boolean | Filter urgent-flagged cases |
| `assigned_to_me` | boolean | Filter to current user's assignments |
| `sort_by` | string | Sort field (default: `created_at`) |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

**Response:** `PaginatedResponse[RescueRequestResponse]`

---

### Soft Delete Rescue Request

**`DELETE /rescue/{request_id}`**

Soft-deletes a rescue request. Requires `rescue:execute` permission.

**Response:**

```json
{
  "success": true,
  "message": "Rescue request deleted successfully."
}
```

---

### Bulk Operations

**`POST /rescue/bulk/status-update`**

Bulk updates rescue request statuses. Requires `rescue:execute` permission.

**Request Body:**

```json
{
  "ids": ["uuid-1", "uuid-2"],
  "status": "verified"
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "message": "2 rescue request(s) status updated.",
    "updated_count": 2
  }
}
```

**`POST /rescue/bulk/delete`**

Bulk soft-deletes rescue requests. Requires `rescue:execute` permission.

**Request Body:**

```json
{
  "ids": ["uuid-1", "uuid-2"]
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "message": "2 rescue request(s) deleted.",
    "deleted_count": 2
  }
}
```

---

### Agent Location Update

**`POST /rescue/agents/location`**

Updates the current GPS position of a rescue agent. Requires `rescue:execute` permission.

**Request Body:**

```json
{
  "latitude": 17.4482,
  "longitude": 78.3741
}
```

**Response:**

```json
{
  "success": true,
  "message": "Agent location updated."
}
```

---

### Suggest Nearest Agents

**`GET /rescue/{request_id}/suggest-agents`**

Suggests the nearest active agents for a rescue request. Requires `rescue:dispatch` permission.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `radius` | float | 50.0 | Search radius in km (0.1-500) |

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "agent_id": "agent-uuid",
      "name": "Agent Smith",
      "email": "agent@example.com",
      "phone": "+1-555-0100",
      "distance_km": 2.4,
      "latitude": 17.4500,
      "longitude": 78.3700
    }
  ],
  "message": "Nearby agents suggested."
}
```

---

### List Agent Availability

**`GET /rescue/agents/availability`**

Lists rescue agents with dynamic availability status. Requires `rescue:dispatch` permission.

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "agent_id": "agent-uuid",
      "name": "Agent Smith",
      "status": "available",
      "active_dispatch_id": null,
      "last_heartbeat": "2026-08-18T10:30:00Z",
      "latitude": 17.4500,
      "longitude": 78.3700
    }
  ],
  "message": "Agent availability retrieved."
}
```

---

### List Vehicle Availability

**`GET /rescue/vehicles/availability`**

Lists fleet vehicles with availability derived from active dispatches. Requires `rescue:dispatch` permission.

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "vehicle_id": "vehicle-uuid",
      "license_plate": "RESCUE-01",
      "vehicle_type": "rescue_van",
      "operational_status": "active",
      "availability": "available",
      "active_dispatch_id": null
    }
  ],
  "message": "Vehicle availability retrieved."
}
```

---

### GPS Tracking

**`POST /rescue/{request_id}/tracking/start`**

Begins GPS tracking for a dispatched rescue operation. Requires `rescue:execute` permission.

**Response:**

```json
{
  "success": true,
  "data": {
    "request_id": "rescue-uuid",
    "tracking_active": true,
    "started_at": "2026-08-18T10:30:00Z",
    "stopped_at": null
  },
  "message": "GPS tracking started."
}
```

**`POST /rescue/{request_id}/tracking/stop`**

Stops GPS tracking. Requires `rescue:execute` permission.

**Response:** Same structure with `tracking_active: false`.

---

### Get Rescue Location

**`GET /rescue/{request_id}/location`**

Retrieves latest GPS positions for assigned agents. Requires `rescue:read` permission.

**Response:**

```json
{
  "success": true,
  "data": {
    "request_id": "rescue-uuid",
    "agents": [
      {
        "agent_id": "agent-uuid",
        "latitude": 17.4482,
        "longitude": 78.3741,
        "last_heartbeat": "2026-08-18T10:30:00Z",
        "updated_at": "2026-08-18T10:30:00Z"
      }
    ],
    "vehicle": null,
    "updated_at": "2026-08-18T10:30:00Z"
  },
  "message": "Rescue location retrieved."
}
```

---

### List Rescue Events

**`GET /rescue/{request_id}/events`**

Retrieves the audit event trail for a rescue case. Requires `rescue:read` permission.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `page_size` | integer | 20 | Items per page |

**Response:** `PaginatedResponse[RescueEventResponse]`

```json
{
  "success": true,
  "data": [
    {
      "event_type": "rescue_reported",
      "actor_id": "user-uuid",
      "created_at": "2026-08-18T10:30:00Z",
      "metadata": null
    }
  ],
  "meta": {
    "total": 5,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```
