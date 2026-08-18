# Fleet Module

Vehicle fleet, equipment lifecycle, fuel logging, and maintenance tracking for PawGuard rescue operations.

## Purpose

The Fleet module manages the complete lifecycle of rescue vehicles, field equipment, fuel consumption, and preventive maintenance. It integrates directly with the Rescue dispatch workflow to auto-checkout and auto-release equipment tied to field operations, and enforces business rules that keep vehicles operational and audit trails complete.

**Supported clients:** Admin Portal, Staff Flutter App, Executive Flutter App.

---

## Architecture

```
Client → Router → FleetService → FleetRepository → Database
```

- **Router** — authenticates, authorises, validates, delegates to service.
- **FleetService** — owns all vehicle, equipment, fuel, and maintenance business logic.
- **FleetRepository** — data access only, no business decisions.

---

## Models

### Vehicle

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Primary key |
| `make_model` | String(255) | NOT NULL | Vehicle make and model |
| `license_plate` | String(64) | UNIQUE, NOT NULL, INDEX | Unique registration plate |
| `vehicle_type` | Enum | INDEX | `rescue_van`, `ambulance`, `mobile_vet_unit`, `utility`, `other` |
| `status` | Enum | NOT NULL | `active`, `in_maintenance`, `out_of_service` |
| `mileage` | Integer | NOT NULL, default 0 | Current odometer reading |
| `primary_driver_id` | UUID FK | nullable, INDEX | Assigned primary driver (`users.id`) |
| `insurance_provider` | String(255) | nullable | Insurance company name |
| `insurance_policy_number` | String(128) | nullable | Policy number |
| `insurance_expiry_date` | Date | nullable | Policy expiry date |
| `insurance_contact_phone` | String(32) | nullable | Insurance contact number |

**Mixins:** `UUIDPkMixin`, `TimestampMixin`, `SoftDeleteMixin`, `AuditMixin`.

### FleetMaintenance

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Primary key |
| `vehicle_id` | UUID FK | NOT NULL, INDEX | Parent vehicle (`vehicles.id`) |
| `service_date` | Date | NOT NULL | Date service was performed |
| `description` | Text | NOT NULL | Service description |
| `cost` | Numeric(10,2) | NOT NULL, default 0 | Service cost |
| `next_due_date` | Date | nullable | Next scheduled service date |

**Mixins:** `UUIDPkMixin`, `TimestampMixin`, `AuditMixin`.

### EquipmentCheckout

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Primary key |
| `equipment_name` | String(255) | NOT NULL | Equipment identifier (e.g. "Net Gun", "Crate") |
| `assigned_to_agent_id` | UUID FK | nullable, INDEX | Assigned staff member (`users.id`) |
| `assigned_to_vehicle_id` | UUID FK | nullable, INDEX | Assigned vehicle (`vehicles.id`) |
| `rescue_dispatch_id` | UUID FK | nullable, INDEX | Links to dispatch for auto-release (`rescue_dispatches.id`) |
| `checked_out_at` | DateTime(tz) | NOT NULL | Checkout timestamp |
| `expected_return_at` | DateTime(tz) | nullable, INDEX | Due date (default +14 days) |
| `returned_at` | DateTime(tz) | nullable | Actual return timestamp |
| `notes` | Text | nullable | Free-text notes; late returns flagged here |

**Mixins:** `UUIDPkMixin`, `TimestampMixin`, `AuditMixin`.

### FuelLog

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Primary key |
| `vehicle_id` | UUID FK | NOT NULL, INDEX | Parent vehicle (`vehicles.id`) |
| `filled_by_id` | UUID FK | nullable, INDEX | Staff who logged the fill (`users.id`) |
| `fuel_type` | String(32) | NOT NULL | Fuel type (e.g. "Diesel", "Petrol") |
| `volume_litres` | Numeric(8,2) | NOT NULL | Volume in litres |
| `cost` | Numeric(10,2) | NOT NULL | Total cost |
| `mileage_at_fill` | Integer | NOT NULL | Odometer reading at time of fill |
| `vendor` | String(255) | nullable | Filling station name |
| `receipt_url` | String(512) | nullable | S3 URL to receipt image |
| `notes` | Text | nullable | Free-text notes |
| `filled_at` | DateTime(tz) | NOT NULL | Fill timestamp |

**Mixins:** `UUIDPkMixin`, `TimestampMixin`, `AuditMixin`.

---

## Endpoints (17)

### Vehicle CRUD

| # | Method | Path | Permission | Description |
|---|---|---|---|---|
| 1 | `POST` | `/fleet/vehicles` | `vehicle:update` | Register a new vehicle (unique license plate enforced) |
| 2 | `GET` | `/fleet/vehicles` | `vehicle:read` | List vehicles (paginated, searchable, filterable by status/type) |
| 3 | `GET` | `/fleet/vehicles/{vehicle_id}` | `vehicle:read` | Get a single vehicle |
| 4 | `PUT` | `/fleet/vehicles/{vehicle_id}` | `vehicle:update` | Update vehicle details (plate uniqueness re-validated) |
| 5 | `PATCH` | `/fleet/vehicles/{vehicle_id}/status` | `vehicle:update` | Update vehicle status only |
| 6 | `DELETE` | `/fleet/vehicles/{vehicle_id}` | `vehicle:update` | Soft-delete a vehicle |

### Bulk Operations

| # | Method | Path | Permission | Description |
|---|---|---|---|---|
| 7 | `POST` | `/fleet/bulk/status-update` | `vehicle:update` | Bulk update vehicle status |
| 8 | `POST` | `/fleet/bulk/delete` | `vehicle:update` | Bulk soft-delete vehicles |

### Maintenance

| # | Method | Path | Permission | Description |
|---|---|---|---|---|
| 9 | `POST` | `/fleet/maintenance` | `vehicle:update` | Log a maintenance record for a vehicle |
| 10 | `GET` | `/fleet/vehicles/{vehicle_id}/maintenance` | `vehicle:read` | List maintenance history (paginated) |

### Equipment

| # | Method | Path | Permission | Description |
|---|---|---|---|---|
| 11 | `POST` | `/fleet/equipment` | `vehicle:update` | Manual equipment checkout |
| 12 | `GET` | `/fleet/equipment` | `vehicle:read` | List equipment checkouts (paginated, `outstanding_only` filter) |
| 13 | `GET` | `/fleet/equipment/{checkout_id}` | `vehicle:read` | Get a single checkout record |
| 14 | `POST` | `/fleet/equipment/{checkout_id}/return` | `vehicle:update` | Return checked-out equipment (flags late returns) |

### Fuel

| # | Method | Path | Permission | Description |
|---|---|---|---|---|
| 15 | `POST` | `/fleet/vehicles/{vehicle_id}/fuel` | `vehicle:update` | Log a fuel fill (auto-updates vehicle mileage) |
| 16 | `GET` | `/fleet/vehicles/{vehicle_id}/fuel` | `vehicle:read` | List fuel logs for a vehicle (paginated) |
| 17 | `GET` | `/fleet/fuel/{log_id}` | `vehicle:read` | Get a single fuel log |

---

## Business Rules

### Vehicle Management

- **Unique license plate:** `POST /vehicles` and `PUT /vehicles/{id}` enforce uniqueness on `license_plate`. A `ConflictError` is returned if the plate already exists on an active vehicle.
- **Status lifecycle:** Vehicles transition between `ACTIVE`, `IN_MAINTENANCE`, and `OUT_OF_SERVICE`. The dedicated `PATCH /vehicles/{id}/status` endpoint exists for status-only updates.
- **Primary driver validation:** If `primary_driver_id` is provided, the referenced user must exist; otherwise a `NotFoundError` is raised.

### Equipment Checkout

- **Manual checkout:** `POST /fleet/equipment` records a checkout with `equipment_name`, optional `assigned_to_agent_id`, `assigned_to_vehicle_id`, and `expected_return_at`.
- **Default return window:** If `expected_return_at` is not provided, it defaults to **14 days** from checkout time (`DEFAULT_CHECKOUT_DURATION`).
- **Past date rejection:** An explicit `expected_return_at` in the past is rejected with a `ConflictError`.
- **Return and late flagging:** On return (`POST /fleet/equipment/{id}/return`), if `returned_at > expected_return_at`, a late return note is appended to `notes`. Late returns are **never rejected** — they are flagged for staff follow-up.
- **Already-returned guard:** Attempting to return equipment that has already been returned raises a `ConflictError`.

### Rescue Dispatch Integration

- **Auto-checkout:** `FleetService.checkout_equipment_for_dispatch()` is called by the rescue module when a dispatch is created. It creates one `EquipmentCheckout` record per equipment name, linking them to the `rescue_dispatch_id`. Each checkout gets the default 14-day return window.
- **Auto-release:** `FleetService.release_equipment_for_dispatch()` marks all outstanding equipment checkouts for a given dispatch as returned (sets `returned_at` to now). This is triggered when a dispatch reaches `ADMITTED` or `REJECTED` status.
- **Session atomicity:** Dispatch-integrated checkouts share the same database session as the dispatch record, ensuring atomicity.

### Fuel Logging

- **Auto-updates vehicle mileage:** When `mileage_at_fill > vehicle.mileage`, the vehicle's `mileage` field is updated. This enforces **forward-only** mileage — the odometer never goes backwards.
- **Audit trail:** Every fuel log records `filled_by_id` from the authenticated user.

### Maintenance Tracking

- **Service record fields:** `service_date`, `description`, `cost`, and optional `next_due_date` for scheduling future service.
- **Vehicle existence check:** Maintenance cannot be logged against a non-existent vehicle.

---

## Scheduled Workers

The following ARQ background workers are configured for proactive fleet management:

| Worker | Schedule | Action |
|---|---|---|
| **Maintenance Due** | Every day | Finds vehicles where `next_due_date` is within **14 days** and sends a notification to the fleet manager. |
| **Insurance Expiry** | Every day | Finds vehicles where `insurance_expiry_date` is within **30 days** and sends an expiry warning. |
| **Overdue Equipment** | Every day | Finds outstanding equipment checkouts past `expected_return_at` and sends reminder notifications. |

---

## Permissions

| Permission | Scope |
|---|---|
| `vehicle:read` | View vehicles, maintenance records, fuel logs, equipment checkouts |
| `vehicle:create` | Register new vehicles |
| `vehicle:update` | Update vehicles, log maintenance/fuel, manage equipment, bulk operations |

---

## Audit Events

Every mutating operation emits an audit event via `AuditService`:

| Event | Trigger |
|---|---|
| `FLEET_VEHICLE_CREATED` | Vehicle registration |
| `FLEET_VEHICLE_UPDATED` | Vehicle update, status change, maintenance log, fuel log |
| `FLEET_VEHICLE_DELETED` | Vehicle soft-delete |
| `FLEET_EQUIPMENT_CHECKED_OUT` | Manual or dispatch-integrated checkout |
| `FLEET_EQUIPMENT_RETURNED` | Equipment return or dispatch auto-release |

---

## Error Handling

| Error | HTTP | When |
|---|---|---|
| `ConflictError` | 409 | Duplicate license plate, already-returned equipment, past return date |
| `NotFoundError` | 404 | Vehicle, equipment checkout, or fuel log not found |

---

## File Structure

```
modules/fleet/
├── __init__.py
├── models.py          # ORM models: Vehicle, FleetMaintenance, EquipmentCheckout, FuelLog
├── schemas.py         # Pydantic request/response schemas
├── repository.py      # Data access layer
├── service.py         # Business logic (FleetService)
└── router.py          # FastAPI router (17 endpoints)
```
