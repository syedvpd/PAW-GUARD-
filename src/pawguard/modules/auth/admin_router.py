"""Admin endpoints: user provisioning, role/permission CRUD.

Every endpoint enforces ``require_permission("system:admin")`` so only
Super Administrators can access these.
"""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.rate_limiter import resolve_client_ip
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.admin_schemas import (
    AdminRestorePasswordRequest,
    AdminUserCreateRequest,
    AdminUserResponse,
    AdminUserUpdateRequest,
    PermissionResponse,
    RoleCreateRequest,
    RoleResponse,
    RoleUpdateRequest,
)
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.auth.repository import (
    PermissionRepository,
    RoleRepository,
    UserRepository,
    UserRoleRepository,
)
from pawguard.modules.auth.service import AdminService
from pawguard.redis.client import RedisClient, get_redis
from pawguard.services.audit_service import AuditService

admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _get_admin_service(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> AdminService:
    return AdminService(
        user_repo=UserRepository(db),
        role_repo=RoleRepository(db),
        permission_repo=PermissionRepository(db),
        user_role_repo=UserRoleRepository(db),
        audit_service=AuditService(db),
        redis=redis,
    )


# ── Role CRUD ────────────────────────────────────────────────────────────────

@admin_router.get(
    "/roles",
    response_model=ApiResponse[list[RoleResponse]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def list_roles(
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[list[RoleResponse]]:
    roles = await service.list_roles()
    return ApiResponse(data=roles)


@admin_router.post(
    "/roles",
    response_model=ApiResponse[RoleResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_role(
    payload: RoleCreateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[RoleResponse]:
    role = await service.create_role(
        name=payload.name,
        description=payload.description,
        permission_codes=payload.permission_codes,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(data=role)


@admin_router.get(
    "/roles/{role_id}",
    response_model=ApiResponse[RoleResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_role(
    role_id: uuid.UUID,
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[RoleResponse]:
    role = await service.get_role(role_id)
    return ApiResponse(data=role)


@admin_router.put(
    "/roles/{role_id}",
    response_model=ApiResponse[RoleResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[RoleResponse]:
    role = await service.update_role(
        role_id,
        description=payload.description,
        permission_codes=payload.permission_codes,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(data=role)


@admin_router.delete(
    "/roles/{role_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def delete_role(
    role_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[None]:
    await service.delete_role(
        role_id,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(message="Role deleted.")


# ── Permission CRUD ──────────────────────────────────────────────────────────

@admin_router.get(
    "/permissions",
    response_model=ApiResponse[list[PermissionResponse]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def list_permissions(
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[list[PermissionResponse]]:
    perms = await service.list_permissions()
    return ApiResponse(data=perms)


# ── User provisioning ────────────────────────────────────────────────────────

@admin_router.get(
    "/users",
    response_model=ApiResponse[list[AdminUserResponse]],
    dependencies=[
        Depends(
            require_permission(
                "system:admin",
                "rescue:read",
                "rescue:dispatch",
                "rescue:write",
                "users:read",
            )
        )
    ],
)
async def list_users(
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[list[AdminUserResponse]]:
    users = await service.list_users()
    return ApiResponse(data=users)


@admin_router.post(
    "/users",
    response_model=ApiResponse[AdminUserResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_user(
    payload: AdminUserCreateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[AdminUserResponse]:
    user = await service.create_user(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone=payload.phone,
        role_names=payload.role_names,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(data=user)


@admin_router.get(
    "/users/{user_id}",
    response_model=ApiResponse[AdminUserResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_user(
    user_id: uuid.UUID,
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[AdminUserResponse]:
    user = await service.get_user(user_id)
    return ApiResponse(data=user)


@admin_router.put(
    "/users/{user_id}",
    response_model=ApiResponse[AdminUserResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[AdminUserResponse]:
    user = await service.update_user(
        user_id,
        full_name=payload.full_name,
        phone=payload.phone,
        is_active=payload.is_active,
        role_names=payload.role_names,
        password=payload.password,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(data=user)


@admin_router.delete(
    "/users/{user_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[None]:
    await service.delete_user(
        user_id,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(message="User soft-deleted.")


@admin_router.post(
    "/users/restore-and-reset",
    response_model=ApiResponse[AdminUserResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def restore_and_reset_password(
    payload: AdminRestorePasswordRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[AdminUserResponse]:
    user = await service.restore_and_reset_password(
        email=payload.email,
        password=payload.password,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(data=user)
