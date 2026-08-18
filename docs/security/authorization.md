# RBAC Authorization System

## Overview

PawGuard implements Role-Based Access Control (RBAC) with permission codes. The system uses Redis caching for performance and supports admin bypass for super_admin roles.

## Permission Code Structure

Permission codes follow the convention: `<module>:<action>`

Examples:
- `rescue:create` - Create rescue requests
- `medical:clearance` - Issue medical clearance
- `adoption:approve` - Approve adoption applications
- `finance:reconcile` - Reconcile financial records

## Registered Permission Codes

### System
- `system:read`, `system:write`, `system:admin`

### User Management
- `user:read`, `user:create`, `user:update`, `user:delete`, `user:assign_role`

### Rescue Operations
- `rescue:create`, `rescue:read`, `rescue:update`, `rescue:delete`
- `rescue:verify`, `rescue:dispatch`, `rescue:execute`

### Vehicle / Fleet
- `vehicle:read`, `vehicle:assign`, `vehicle:update`

### Shelter / Facility
- `shelter:read`, `shelter:update`, `shelter:manage_kennels`, `shelter:transfer`

### Medical / Veterinary
- `medical:create`, `medical:read`, `medical:update`, `medical:clearance`, `medical:delete`

### Adoption
- `adoption:read`, `adoption:process`, `adoption:approve`, `adoption:lock`, `adoption:delete`

### Foster
- `foster:create`, `foster:read`, `foster:update`, `foster:approve`, `foster:delete`

### Volunteer
- `volunteer:create`, `volunteer:read`, `volunteer:update`, `volunteer:schedule`, `volunteer:delete`

### Inventory
- `inventory:create`, `inventory:read`, `inventory:update`, `inventory:delete`

### Finance
- `finance:read`, `finance:create`, `finance:reconcile`, `finance:update`, `finance:delete`, `finance:export`

### Reports
- `reports:read`, `reports:create`, `reports:export_pdf`, `reports:export_csv`, `reports:export_excel`

### Dashboards
- `dashboard:rescue`, `dashboard:shelter`, `dashboard:medical`, `dashboard:adoption`
- `dashboard:foster`, `dashboard:volunteer`, `dashboard:inventory`, `dashboard:finance`, `dashboard:donor`

### Donation / Sponsorship
- `donation:read`, `donation:manage`, `donation:update`

### Public Portal
- `public:read`, `public:create`

### Audit
- `audit:read`

### Grievance
- `grievance:create`, `grievance:read`, `grievance:update`, `grievance:assign`, `grievance:comment`

### Notifications
- `notification:read`, `notification:manage`

### Client-Facing Aliases
- `rescue:write` (alias for rescue:create/update/delete)
- `donations:write` (alias for donation:manage/update)
- `complaints:write` (alias for grievance:*)
- `notifications:write` (alias for notification:manage)

### Companion Pets
- `companion_pet:create`, `companion_pet:read`, `companion_pet:update`, `companion_pet:delete`
- `companion_pet:medical_upload`, `safety_tag:manage`
- `vet_clinic:read`, `vet_clinic:manage`
- `appointment:create`, `appointment:read`, `appointment:cancel`, `appointment:manage`

## Admin Bypass Roles

```python
ADMIN_ROLES = {
    "super_admin",
    "system:admin",
}
```

Users with these roles bypass all permission checks. This is the only bypass mechanism.

## Permission Resolution Flow

```python
class RequirePermission:
    async def __call__(self, current: CurrentUser):
        # 1. Check admin bypass
        if is_admin_role(current.claims):
            return current

        # 2. Check Redis cache for role permissions
        cache_key = f"roles:{':'.join(sorted(current.claims.roles))}"
        codes = await cache.get(cache_key)

        if codes is None:
            # 3. Query database for role permissions
            codes = sorted(await get_role_permission_codes(current.db, current.claims.roles))
            await cache.set(cache_key, codes, ttl_seconds=300)

        # 4. Verify permission exists
        if self.permission_code not in codes:
            raise InsufficientPermissionsError(...)
```

## Usage in Routers

```python
from pawguard.modules.auth.rbac import require_permission

@router.post("/rescue")
async def create_rescue(
    current: CurrentUser = Depends(require_permission("rescue:create")),
):
    # Only users with rescue:create permission reach here
    ...
```

## Cache Invalidation

When roles are created, updated, or deleted via `AdminService`:
```python
async def _invalidate_rbac_cache(self):
    await CacheService(self._redis, namespace="rbac").delete_prefix("roles")
```

## Database Schema

### roles
- `id` (UUID, PK)
- `name` (String(64), unique)
- `description` (String(255), nullable)
- `is_system` (Boolean) - system roles cannot be modified/deleted

### permissions
- `id` (UUID, PK)
- `code` (String(128), unique)
- `description` (String(255), nullable)

### role_permissions
- `role_id` (UUID, FK to roles)
- `permission_id` (UUID, FK to permissions)

### user_roles
- `user_id` (UUID, FK to users)
- `role_id` (UUID, FK to roles)

## Role Management (Admin)

### Endpoints
- `GET /admin/roles` - List all roles
- `POST /admin/roles` - Create role with permissions
- `PUT /admin/roles/{role_id}` - Update role
- `DELETE /admin/roles/{role_id}` - Delete role (non-system only)

### User Provisioning
- `POST /admin/users` - Create user with roles
- `PUT /admin/users/{user_id}` - Update user, roles, password
- `DELETE /admin/users/{user_id}` - Soft delete user
