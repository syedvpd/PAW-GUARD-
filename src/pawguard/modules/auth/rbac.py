"""RBAC/PBAC permission resolution with Redis-cached role->permission lookups."""

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.exceptions import InsufficientPermissionsError
from pawguard.modules.auth.models import Permission, Role, RolePermission, User
from pawguard.services.cache_service import CacheService

PERMISSIONS_CACHE_TTL_SECONDS = 300

# Roles that bypass all permission checks (unrestricted access).
# PRR 2.1 least-privilege: ONLY super_admin bypasses. Every other role
# (including rescue_centre_admin, rescue_admin, shelter_admin, admin)
# authenticates against the seeded permission set; adding them here would
# grant unrestricted super-admin access regardless of what the seed
# script grants, which violates PRR 2.1.
ADMIN_ROLES = {
    "super_admin",
    "system:admin",
}


def is_admin_role(claims) -> bool:
    """True when the token carries a role with unrestricted admin access."""
    return any(r in ADMIN_ROLES for r in claims.roles)


def has_permission(user: User, permission_code: str) -> bool:
    """Direct role->permission check on an in-memory User object.

    Used by owner-or-permission endpoint guards (e.g. a donor reading their own
    receipt) where a full `require_permission` dependency would be too coarse.
    """
    return any(
        permission_code == p.code for r in user.roles for p in r.permissions
    )


async def get_role_permission_codes(session: AsyncSession, role_names: list[str]) -> set[str]:
    if not role_names:
        return set()
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name.in_(role_names))
    )
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


class RequirePermission:
    """FastAPI dependency: `Depends(RequirePermission("rescue:create", "rescue:dispatch"))`."""

    def __init__(self, *permission_codes: str) -> None:
        self.permission_codes = permission_codes

    async def __call__(self, current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        # Admin bypass — super_admin, system:admin, and admin roles have unrestricted access
        if is_admin_role(current.claims):
            return current

        cache = CacheService(current.redis, namespace="rbac")
        cache_key = f"roles:{':'.join(sorted(current.claims.roles))}"

        codes = await cache.get(cache_key)
        if codes is None:
            codes = sorted(await get_role_permission_codes(current.db, current.claims.roles))
            await cache.set(cache_key, codes, ttl_seconds=PERMISSIONS_CACHE_TTL_SECONDS)

        if not any(code in codes or "system:admin" in codes for code in self.permission_codes):
            req_str = ", ".join(self.permission_codes)
            raise InsufficientPermissionsError(
                f"Missing required permission: {req_str}"
            )
        return current


def require_permission(*permission_codes: str) -> RequirePermission:
    return RequirePermission(*permission_codes)
