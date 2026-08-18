# Rescue Centre Module

Alias router for shelter facility management — provides `/rescue-centres` endpoints that delegate to the Shelter module.

---

## Architecture

```
rescue_centre/
  router.py          # 8 endpoints (alias for shelter facilities)
```

This module reuses `ShelterService` directly. It provides a separate URL namespace (`/rescue-centres`) for the rescue centre concept while sharing the same underlying data model.

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/rescue-centres` | Optional auth | List rescue centres |
| POST | `/rescue-centres` | `shelter:update` | Create rescue centre |
| GET | `/rescue-centres/{id}` | Optional auth | Get rescue centre |
| PUT | `/rescue-centres/{id}` | `shelter:update` | Update rescue centre |
| DELETE | `/rescue-centres/{id}` | `shelter:update` | Soft delete |
| PUT | `/rescue-centres/{id}/status` | `shelter:update` | Update status |
| POST | `/rescue-centres/bulk/delete` | `shelter:update` | Bulk soft delete |
| POST | `/rescue-centres/bulk/status` | `shelter:update` | Bulk status |

## Delegation

All operations delegate to `ShelterService` (from `shelter/service.py`):
- `create_facility()`, `list_facilities_paginated()`, `get_facility()`
- `update_facility()`, `soft_delete_facility()`, `update_facility_status()`
- `bulk_delete_facilities()`, `bulk_update_facility_status()`

See [Shelter Module](../shelter/README.md) for full business rules.
