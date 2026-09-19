# Fleet Module

Vehicle fleet management, equipment checkout/release lifecycle, fuel logging, and maintenance tracking.

---

## Architecture

```
fleet/
  router.py          # 27 endpoints
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
| `FleetBreakdownReport` | `fleet_breakdown_reports` | Breakdown reports: reported -> in_repair -> resolved |
| `EquipmentAsset` | `equipment_assets` | High-value capture equipment register (serial, category, condition) |

`FleetMaintenance.maintenance_type` is `service`, `safety_inspection` or `repair`.

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
| GET | `/fleet/maintenance` | `vehicle:read` | List maintenance across the fleet |
| GET | `/fleet/summary` | `vehicle:read` | Status counts, insurance expiring (30d), maintenance due (14d), outstanding/overdue equipment, open breakdowns |
| POST | `/fleet/breakdowns` | `vehicle:update` or `rescue:execute` | Report a breakdown (Rescue Agents report from the field) |
| GET | `/fleet/breakdowns` | `vehicle:read` | List breakdowns (`vehicle_id`, `status` filters) |
| GET | `/fleet/breakdowns/{id}` | `vehicle:read` | Get breakdown |
| PATCH | `/fleet/breakdowns/{id}` | `vehicle:update` | Update breakdown / move status |
| POST | `/fleet/equipment-assets` | `vehicle:update` | Register equipment (serial numbers unique) |
| GET | `/fleet/equipment-assets` | `vehicle:read` | List register with `current_checkout_id` |
| GET | `/fleet/equipment-assets/{id}` | `vehicle:read` | Get asset |
| PUT | `/fleet/equipment-assets/{id}` | `vehicle:update` | Update asset |

`POST /fleet/vehicles` accepts the insurance fields (`insurance_provider`, `insurance_policy_number`, `insurance_expiry_date`, `insurance_contact_phone`).

### Maintenance due

Only a vehicle's most recent maintenance record (by `service_date`) decides when the next service is due. Older records are superseded, so their `next_due_date` never raises an alert. `/fleet/summary` and the `check_fleet_maintenance_due` job share `FleetRepository.list_maintenance_due`.

## Equipment Lifecycle

### Manual Checkout
```
POST /fleet/equipment {asset_id? | equipment_name, assigned_to_agent_id?, expected_return_at?}
  -> Validate vehicle if assigned
  -> asset_id: asset must exist, not be retired, and have no outstanding checkout (409);
     equipment_name defaults to the asset name. A partial unique index
     (uq_equipment_checkouts_asset_outstanding) enforces one open checkout per asset.
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
  -> Optional `condition` updates the linked asset (e.g. needs_repair)
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
