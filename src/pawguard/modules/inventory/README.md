# Inventory Module

Stock management, movements, requisitions, expiry enforcement, and low-stock alerting.

---

## Architecture

```
inventory/
  router.py          # 12 endpoints
  service.py         # InventoryService (stock, movements, requisitions)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `InventoryItem` | `inventory_items` | Stock item: name, category, quantity, reorder threshold, expiry |
| `InventoryMovement` | `inventory_movements` | Stock movement log with reference tracking |
| `RequisitionOrder` | `requisition_orders` | Requisition workflow |

**DB Constraints:** `quantity >= 0`, `unit_cost >= 0`

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/inventory/items` | `inventory:create` | Create item |
| GET | `/inventory/items` | `inventory:read` | List items |
| GET | `/inventory/items/{id}` | `inventory:read` | Get item |
| POST | `/inventory/movements` | `inventory:update` | Record movement |
| GET | `/inventory/items/{id}/movements` | `inventory:read` | List movements |
| POST | `/inventory/requisitions` | `inventory:create` | Create requisition |
| GET | `/inventory/requisitions` | `inventory:read` | List requisitions |
| PUT | `/inventory/requisitions/{id}/status` | `inventory:update` | Update requisition status |
| DELETE | `/inventory/items/{id}` | `inventory:update` | Soft delete |
| POST | `/inventory/items/bulk/delete` | `inventory:update` | Bulk soft delete |
| POST | `/inventory/requisitions/bulk/status` | `inventory:update` | Bulk requisition status |

## Movement Types

| Type | Direction | Effect |
|------|-----------|--------|
| `CHECK_IN` | Inbound | `quantity += qty` |
| `CHECK_OUT` | Outbound | `quantity -= qty` (enforces expiry + stock) |
| `CONSUMPTION` | Outbound | Same as CHECK_OUT |
| `ADJUSTMENT` | Absolute | `quantity = qty` (overwrite) |

## Stock Movement Flow

```
POST /inventory/movements {item_id, movement_type, quantity, reference_type?, reference_id?}
  -> Fetch item
  -> If CHECK_OUT/CONSUMPTION:
     -> Expiry check: ConflictError if item.expiry_date is in the past
     -> Stock check: ConflictError if quantity < requested
     -> Subtract from item.quantity
  -> If CHECK_IN:
     -> Add to item.quantity
  -> If ADJUSTMENT:
     -> Set item.quantity = quantity
  -> Create InventoryMovement
  -> If quantity <= reorder_threshold:
     -> Broadcast notification to inventory_manager + rescue_centre_admin
```

## Requisition Workflow

```
PENDING ──approve──> APPROVED ──receive──> RECEIVED (terminal)
   │
   └──reject──> REJECTED (terminal)
```

**Auto-delivery on RECEIVED:** Creates `CHECK_IN` movement for the requisition quantity.

## Cross-Module Consumption

Medical and shelter modules consume inventory via the same pattern:

| Consumer | reference_type | Trigger |
|----------|---------------|---------|
| Medical treatment | `medical_treatment` | `POST /medical/treatments` with `inventory_consumptions` |
| Prescription | `prescription` | `POST /medical/prescriptions` with `inventory_consumptions` |
| Daily care log | `daily_care_log` | `POST /shelter/care-logs` with `inventory_consumptions` |

All consume via `InventoryService.record_movement(CHECK_OUT, ...)` which handles expiry, stock validation, and low-stock alerts.

## Scheduled Workers

| Worker | Frequency | Action |
|--------|-----------|--------|
| `check_inventory_low_stock` | 00:00, 12:00 | Push + in-app for items below reorder threshold |
| `check_inventory_expiry` | 09:00 | Push + in-app for items expiring within 60 days |
