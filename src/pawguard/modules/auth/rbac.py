"""RBAC/PBAC permission resolution with Redis-cached role->permission lookups."""

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.exceptions import InsufficientPermissionsError
from pawguard.modules.auth.models import Permission, Role, RolePermission
from pawguard.services.cache_service import CacheService

PERMISSIONS_CACHE_TTL_SECONDS = 300


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
    """FastAPI dependency: `Depends(RequirePermission("rescue:create"))`."""

    def __init__(self, permission_code: str) -> None:
        self.permission_code = permission_code

    async def __call__(self, current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        cache = CacheService(current.redis, namespace="rbac")
        cache_key = f"roles:{':'.join(sorted(current.claims.roles))}"

        codes = await cache.get(cache_key)
        if codes is None:
            codes = sorted(await get_role_permission_codes(current.db, current.claims.roles))
            await cache.set(cache_key, codes, ttl_seconds=PERMISSIONS_CACHE_TTL_SECONDS)

        if self.permission_code not in codes:
            raise InsufficientPermissionsError(
                f"Missing required permission: {self.permission_code}"
            )
        return current


def require_permission(permission_code: str) -> RequirePermission:
    return RequirePermission(permission_code)
