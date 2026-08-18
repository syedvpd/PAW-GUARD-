# Fleet Module

Vehicle fleet management, equipment checkout/release lifecycle, fuel logging, and maintenance tracking.

---

## Architecture

```
fleet/
  router.py          # 17 endpoints
  service.py         # FleetService (vehicles, equipment, fuel)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `Vehicle` | `vehicles` | Vehicle record: make/model, plate, status, insurance |
| `FleetMaintenance` | `fleet_maintenances` | Service records with next_due_date |
| `EquipmentCheckout` | `equipment_checkouts` | Equipment tracking: who, when, return status |
| `FuelLog` | `fuel_logs` | Fuel fill records with auto mileage update |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/fleet/vehicles` | `vehicle:update` | Register vehicle |
| GET | `/fleet/vehicles` | `vehicle:read` | List vehicles |
| GET | `/fleet/vehicles/{id}` | `vehicle:read` | Get vehicle |
| PUT | `/fleet/vehicles/{id}` | `vehicle:update` | Update vehicle |
| PATCH | `/fleet/vehicles/{id}/status` | `vehicle:update` | Update status |
| DELETE | `/fleet/vehicles/{id}` | `vehicle:update` | Soft delete |
| POST | `/fleet/maintenance` | `vehicle:update` | Log maintenance |
| GET | `/fleet/vehicles/{id}/maintenance` | `vehicle:read` | List maintenance |
| POST | `/fleet/equipment` | `vehicle:update` | Checkout equipment |
| GET | `/fleet/equipment` | `vehicle:read` | List checkouts |
| GET | `/fleet/equipment/{id}` | `vehicle:read` | Get checkout |
| POST | `/fleet/equipment/{id}/return` | `vehicle:update` | Return equipment |
| POST | `/fleet/vehicles/{id}/fuel` | `vehicle:update` | Log fuel |
| GET | `/fleet/vehicles/{id}/fuel` | `vehicle:read` | List fuel logs |
| GET | `/fleet/fuel/{id}` | `vehicle:read` | Get fuel log |
| POST | `/fleet/bulk/status-update` | `vehicle:update` | Bulk status |
| POST | `/fleet/bulk/delete` | `vehicle:update` | Bulk soft delete |

## Equipment Lifecycle

### Manual Checkout
```
POST /fleet/equipment {equipment_name, assigned_to_agent_id?, expected_return_at?}
  -> Validate vehicle if assigned
  -> Set checked_out_at = now
  -> expected_return_at: explicit (must be future) or default now + 14 days
  -> Create EquipmentCheckout
```

### Auto-Checkout for Rescue Dispatch
```
FleetService.checkout_equipment_for_dispatch(rescue_dispatch_id, equipment_names, agent_id)
  -> For each name: create EquipmentCheckout with rescue_dispatch_id linked
  -> Runs in same DB transaction as dispatch (atomic)
```

### Return
```
POST /fleet/equipment/{id}/return
  -> Set returned_at = now
  -> If late (returned_at > expected_return_at): append "Returned late" note
  -> Late returns are flagged, never rejected
```

### Auto-Release for Rescue
```
FleetService.release_equipment_for_dispatch(rescue_dispatch_id)
  -> Bulk-update returned_at on all outstanding checkouts for that dispatch
  -> Called on ADMITTED or REJECTED status
```

## Fuel Logging

- Records: fuel_type, volume, cost, mileage_at_fill, vendor
- **Auto-updates vehicle.mileage** if `mileage_at_fill > current mileage` (forward-only)

## Scheduled Workers

| Worker | Frequency | Action |
|--------|-----------|--------|
| `check_fleet_maintenance_due` | Daily | Push to staff for maintenance due within 14 days |
| `check_vehicle_insurance_expiry` | Daily | Push to staff for insurance expiring within 30 days |
| `check_equipment_checkout_expiry` | Daily | Push to staff for overdue equipment |

## Cross-Module Interactions

| Source | Trigger | Effect |
|--------|---------|--------|
| Rescue | Dispatch created | Auto-checkout equipment |
| Rescue | ADMITTED/REJECTED | Auto-release equipment |
| Medical | Treatment/Prescription | Consumes inventory (separate from fleet) |
