"""RBAC/PBAC permission resolution with Redis-cached role->permission lookups."""

import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.exceptions import InsufficientPermissionsError
from pawguard.modules.auth.models import Permission, Role, RolePermission, User, UserPermission
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
    if claims is None:
        return False
    roles = getattr(claims, "roles", None)
    if roles is None and isinstance(claims, dict):
        roles = claims.get("roles", [])
    return any(r in ADMIN_ROLES for r in (roles or []))


def has_permission(user: User, permission_code: str) -> bool:
    """Direct role->permission check on an in-memory User object.

    Used by owner-or-permission endpoint guards (e.g. a donor reading their own
    receipt) where a full `require_permission` dependency would be too coarse.
    Checks both role-based and user-level direct permission grants.
    """
    if any(permission_code == p.code for r in user.roles for p in r.permissions):
        return True
    if hasattr(user, "user_permissions") and user.user_permissions is not None:
        return any(permission_code == up.code for up in user.user_permissions)
    return False


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


async def get_user_permission_codes(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """Fetch direct user-level permission overrides from the database."""
    stmt = (
        select(Permission.code)
        .join(UserPermission, UserPermission.permission_id == Permission.id)
        .where(UserPermission.user_id == user_id)
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

        # Check role-based permissions (cached)
        role_cache_key = f"roles:{':'.join(sorted(current.claims.roles))}"
        role_codes = await cache.get(role_cache_key)
        if role_codes is None:
            role_codes = sorted(await get_role_permission_codes(current.db, current.claims.roles))
            await cache.set(role_cache_key, role_codes, ttl_seconds=PERMISSIONS_CACHE_TTL_SECONDS)

        if any(
            code in role_codes or "system:admin" in role_codes for code in self.permission_codes
        ):
            return current

        # Check user-level direct permission overrides (cached)
        user_cache_key = f"user:{current.id}:perms"
        user_codes = await cache.get(user_cache_key)
        if user_codes is None:
            user_codes = sorted(await get_user_permission_codes(current.db, current.id))
            await cache.set(user_cache_key, user_codes, ttl_seconds=PERMISSIONS_CACHE_TTL_SECONDS)

        if any(code in user_codes for code in self.permission_codes):
            return current

        req_str = ", ".join(self.permission_codes)
        raise InsufficientPermissionsError(f"Missing required permission: {req_str}")


def require_permission(*permission_codes: str) -> RequirePermission:
    return RequirePermission(*permission_codes)


class RequireRole:
    """FastAPI dependency: `Depends(require_role("veterinarian"))`."""

    def __init__(self, *role_names: str) -> None:
        self.role_names = set(role_names)

    async def __call__(self, current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if is_admin_role(current.claims):
            return current

        user_roles = set(current.claims.roles)
        if hasattr(current.user, "roles") and current.user.roles:
            user_roles.update(r.name for r in current.user.roles)

        if not (self.role_names & user_roles):
            req_str = ", ".join(self.role_names)
            raise InsufficientPermissionsError(f"Missing required role: {req_str}")
        return current


def require_role(*role_names: str) -> RequireRole:
    return RequireRole(*role_names)
