# Admin Module

Admin dashboard aggregation and user/role management endpoints.

---

## Architecture

```
admin/
  admin_router.py    # Admin user/role management endpoints
  dashboard_repository.py  # Dashboard aggregation queries
  dashboard_router.py      # Dashboard API endpoints
```

## Admin User/Role Management

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/admin/roles` | `system:admin` | Create role |
| PUT | `/admin/roles/{id}` | `system:admin` | Update role |
| DELETE | `/admin/roles/{id}` | `system:admin` | Delete role |
| POST | `/admin/users` | `system:admin` | Create user |
| PUT | `/admin/users/{id}` | `system:admin` | Update user |
| DELETE | `/admin/users/{id}` | `system:admin` | Delete user |
| POST | `/admin/users/{id}/reset-password` | `system:admin` | Reset user password |

## Dashboard Aggregation

The `DashboardRepository` provides cross-module aggregation queries used by the Dashboards module. It reads from all domain tables to produce summary statistics.

See [Dashboards Module](../dashboards/README.md) for endpoint details.
