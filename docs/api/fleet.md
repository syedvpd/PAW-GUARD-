# Fleet Management API

## Overview

The Fleet module manages rescue vehicles, maintenance records, equipment checkout/return, and fuel logs. It supports the rescue dispatch workflow by tracking vehicle availability and equipment assignment.

**Prefix:** `/api/v1/fleet`

---

## Endpoints

### Vehicles

#### Create Vehicle

**`POST /fleet/vehicles`**

Registers a new vehicle. Requires `vehicle:update` permission.

**Request Body:**

```json
{
  "make_model": "Ford Transit 2022",
  "license_plate": "RESCUE-01",
  "vehicle_type": "rescue_van",
  "status": "active",
  "mileage": 12500,
  "primary_driver_id": "driver-uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `make_model` | string | Yes | Vehicle make and model |
| `license_plate` | string | Yes | License plate (unique) |
| `vehicle_type` | string | No | `rescue_van`, `ambulance`, `mobile_vet_unit`, `utility`, `other` |
| `status` | string | No | `active`, `in_maintenance`, `out_of_service` |
| `mileage` | integer | No | Current mileage (default: 0) |
| `primary_driver_id` | UUID | No | Assigned primary driver |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "vehicle-uuid",
    "make_model": "Ford Transit 2022",
    "license_plate": "RESCUE-01",
    "vehicle_type": "rescue_van",
    "status": "active",
    "mileage": 12500,
    "primary_driver_id": "driver-uuid",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Vehicle registered."
}
```

---

#### List Vehicles

**`GET /fleet/vehicles`**

Lists vehicles with filtering and pagination. Requires `vehicle:read` permission.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |
| `search` | string | Search by make/model, license plate |
| `status` | string | Filter by status |
| `vehicle_type` | string | Filter by vehicle type |
| `sort_by` | string | Sort field (default: `created_at`) |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

**Response:** `PaginatedResponse[VehicleResponse]`

---

#### Get Vehicle

**`GET /fleet/vehicles/{vehicle_id}`**

Returns a single vehicle. Requires `vehicle:read` permission.

**Response:** `VehicleResponse` object.

---

#### Update Vehicle

**`PUT /fleet/vehicles/{vehicle_id}`**

Updates a vehicle. Requires `vehicle:update` permission.

**Request Body:**

```json
{
  "make_model": "Ford Transit 2023",
  "license_plate": "RESCUE-01",
  "vehicle_type": "rescue_van",
  "status": "active",
  "mileage": 12800,
  "primary_driver_id": "new-driver-uuid",
  "insurance_provider": "SafeGuard Insurance Co.",
  "insurance_policy_number": "POL-2026-004521",
  "insurance_expiry_date": "2027-01-31",
  "insurance_contact_phone": "+1-555-0188"
}
```

**Response:** Updated `VehicleResponse` object.

---

#### Update Vehicle Status

**`PATCH /fleet/vehicles/{vehicle_id}/status`**

Updates vehicle status. Requires `vehicle:update` permission.

**Request Body:**

```json
{
  "status": "in_maintenance"
}
```

**Response:** Updated `VehicleResponse` object.

---

#### Delete Vehicle

**`DELETE /fleet/vehicles/{vehicle_id}`**

Soft-deletes a vehicle. Requires `vehicle:update` permission.

**Response:**

```json
{
  "success": true,
  "message": "Vehicle deleted successfully."
}
```

---

### Maintenance

#### Log Maintenance

**`POST /fleet/maintenance`**

Logs a maintenance record. Requires `vehicle:update` permission.

**Request Body:**

```json
{
  "vehicle_id": "vehicle-uuid",
  "service_date": "2026-07-15",
  "description": "Oil change and brake inspection",
  "cost": 150.00,
  "next_due_date": "2027-01-15"
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "maint-uuid",
    "vehicle_id": "vehicle-uuid",
    "service_date": "2026-07-15",
    "description": "Oil change and brake inspection",
    "cost": 150.0,
    "next_due_date": "2027-01-15",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Maintenance logged."
}
```

---

#### List Maintenance Records

**`GET /fleet/vehicles/{vehicle_id}/maintenance`**

Lists maintenance records for a vehicle. Requires `vehicle:read` permission.

**Response:** `PaginatedResponse[MaintenanceResponse]`

---

### Equipment

#### Checkout Equipment

**`POST /fleet/equipment`**

Checks out equipment to an agent or vehicle. Requires `vehicle:update` permission.

**Request Body:**

```json
{
  "equipment_name": "Net Gun",
  "assigned_to_agent_id": "agent-uuid",
  "assigned_to_vehicle_id": "vehicle-uuid",
  "expected_return_at": "2026-08-17T18:00:00Z",
  "notes": "Checked out for Sector 4 rescue."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `equipment_name` | string | Yes | Name of the equipment |
| `assigned_to_agent_id` | UUID | No | Agent receiving the equipment |
| `assigned_to_vehicle_id` | UUID | No | Vehicle the equipment is assigned to |
| `expected_return_at` | datetime | No | Expected return time |
| `notes` | string | No | Additional notes |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "checkout-uuid",
    "equipment_name": "Net Gun",
    "assigned_to_agent_id": "agent-uuid",
    "assigned_to_vehicle_id": "vehicle-uuid",
    "rescue_dispatch_id": null,
    "checked_out_at": "2026-08-18T10:30:00Z",
    "expected_return_at": "2026-08-17T18:00:00Z",
    "returned_at": null,
    "notes": "Checked out for Sector 4 rescue.",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Equipment checked out."
}
```

---

#### List Equipment Checkouts

**`GET /fleet/equipment`**

Lists equipment checkouts. Requires `vehicle:read` permission.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |
| `search` | string | Search by equipment name, notes |
| `outstanding_only` | boolean | Only show equipment not yet returned |
| `sort_by` | string | Sort field (default: `checked_out_at`) |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

**Response:** `PaginatedResponse[EquipmentCheckoutResponse]`

---

#### Get Equipment Checkout

**`GET /fleet/equipment/{checkout_id}`**

Returns a single equipment checkout record. Requires `vehicle:read` permission.

---

#### Return Equipment

**`POST /fleet/equipment/{checkout_id}/return`**

Records equipment return. Requires `vehicle:update` permission.

**Request Body:**

```json
{
  "notes": "Returned in good condition."
}
```

**Response:** Updated `EquipmentCheckoutResponse` object.

---

### Fuel Logs

#### Log Fuel

**`POST /fleet/vehicles/{vehicle_id}/fuel`**

Logs a fuel fill-up. Requires `vehicle:update` permission.

**Request Body:**

```json
{
  "fuel_type": "Diesel",
  "volume_litres": 45.5,
  "cost": 68.25,
  "mileage_at_fill": 12750,
  "vendor": "Shell Gas Station",
  "receipt_url": "https://example.com/receipt.jpg",
  "notes": "Full tank before long-distance dispatch."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fuel_type` | string | Yes | Type of fuel |
| `volume_litres` | float | Yes | Volume in litres |
| `cost` | float | Yes | Total cost |
| `mileage_at_fill` | integer | Yes | Odometer reading at fill |
| `vendor` | string | No | Gas station/vendor name |
| `receipt_url` | string | No | URL to receipt image |
| `notes` | string | No | Additional notes |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "fuel-uuid",
    "vehicle_id": "vehicle-uuid",
    "filled_by_id": "user-uuid",
    "fuel_type": "Diesel",
    "volume_litres": 45.5,
    "cost": 68.25,
    "mileage_at_fill": 12750,
    "vendor": "Shell Gas Station",
    "receipt_url": "https://example.com/receipt.jpg",
    "notes": "Full tank before long-distance dispatch.",
    "filled_at": "2026-08-18T10:30:00Z",
    "created_at": "2026-08-18T10:30:00Z"
  },
  "message": "Fuel log created."
}
```

---

#### List Fuel Logs

**`GET /fleet/vehicles/{vehicle_id}/fuel`**

Lists fuel logs for a vehicle. Requires `vehicle:read` permission.

**Response:** `PaginatedResponse[FuelLogResponse]`

---

#### Get Fuel Log

**`GET /fleet/fuel/{log_id}`**

Returns a single fuel log. Requires `vehicle:read` permission.

---

### Bulk Operations

**`POST /fleet/bulk/status-update`**

Bulk updates vehicle statuses. Requires `vehicle:update` permission.

**Request Body:**

```json
{
  "ids": ["vehicle-uuid-1", "vehicle-uuid-2"],
  "status": "active"
}
```

**`POST /fleet/bulk/delete`**

Bulk soft-deletes vehicles. Requires `vehicle:update` permission.

**Request Body:**

```json
{
  "ids": ["vehicle-uuid-1", "vehicle-uuid-2"]
}
```
