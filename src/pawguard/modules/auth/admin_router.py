"""Admin endpoints: user provisioning, role/permission CRUD.

Every endpoint enforces ``require_permission("system:admin")`` so only
Super Administrators can access these.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.cache_decorator import cache_response
from pawguard.core.constants import ClientType
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
    UserPermissionGrantRequest,
)
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.auth.rbac import require_permission, require_role
from pawguard.modules.auth.repository import (
    PermissionRepository,
    RoleRepository,
    UserPermissionRepository,
    UserRepository,
    UserRoleRepository,
)
from pawguard.modules.auth.router import _build_reset_url, get_auth_service
from pawguard.modules.auth.schemas import SessionInfo
from pawguard.modules.auth.service import AdminService, AuthService, RequestContext
from pawguard.modules.outbox.service import OutboxService
from pawguard.redis.client import RedisClient, get_redis
from pawguard.services.audit_service import AuditService

admin_router = APIRouter(prefix="/admin", tags=["admin"])

SUPER_ADMIN_ONLY = [Depends(require_role("super_admin"))]


def _get_admin_service(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> AdminService:
    return AdminService(
        user_repo=UserRepository(db),
        role_repo=RoleRepository(db),
        permission_repo=PermissionRepository(db),
        user_role_repo=UserRoleRepository(db),
        user_permission_repo=UserPermissionRepository(db),
        audit_service=AuditService(db),
        redis=redis,
    )


# ── Role CRUD ────────────────────────────────────────────────────────────────


@admin_router.get(
    "/roles",
    response_model=ApiResponse[list[RoleResponse]],
    dependencies=[Depends(require_permission("system:admin"))],
)
@cache_response(ttl_seconds=60, namespace="admin")
async def list_roles(
    request: Request,
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[list[RoleResponse]]:
    roles = await service.list_roles()
    return ApiResponse(data=[RoleResponse.model_validate(r) for r in roles])


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
    return ApiResponse(data=RoleResponse.model_validate(role))


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
    return ApiResponse(data=RoleResponse.model_validate(role))


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
    return ApiResponse(data=RoleResponse.model_validate(role))


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
@cache_response(ttl_seconds=300, namespace="admin")
async def list_permissions(
    request: Request,
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[list[PermissionResponse]]:
    perms = await service.list_permissions()
    return ApiResponse(data=[PermissionResponse.model_validate(p) for p in perms])


# ── User provisioning ────────────────────────────────────────────────────────


@admin_router.get(
    "/users",
    response_model=ApiResponse[list[AdminUserResponse]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def list_users(
    response: Response,
    page: int = Query(1, ge=1),
    per_page: int | None = Query(
        None, ge=1, le=100, description="Enables paging; without it every user is returned."
    ),
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
    q: str | None = Query(None, max_length=100),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[list[AdminUserResponse]]:
    if per_page is None and role is None and is_active is None and not q:
        users = await service.list_users()
        total = len(users)
    else:
        users, total = await service.search_users(
            page=page, page_size=per_page or 1000, role=role, is_active=is_active, q=q
        )
    response.headers["X-Total-Count"] = str(total)
    return ApiResponse(data=[AdminUserResponse.model_validate(u) for u in users])


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
        can_drive=payload.can_drive,
        managed_facility_id=payload.managed_facility_id,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(data=AdminUserResponse.model_validate(user))


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
    return ApiResponse(data=AdminUserResponse.model_validate(user))


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
    update_kwargs: dict[str, Any] = {
        "full_name": payload.full_name,
        "phone": payload.phone,
        "is_active": payload.is_active,
        "can_drive": payload.can_drive,
        "role_names": payload.role_names,
        "password": payload.password,
        "actor_id": current_user.id,
        "ip_address": resolve_client_ip(request),
        "user_agent": request.headers.get("user-agent"),
    }
    if "managed_facility_id" in payload.model_fields_set:
        update_kwargs["managed_facility_id"] = payload.managed_facility_id

    user = await service.update_user(user_id, **update_kwargs)
    return ApiResponse(data=AdminUserResponse.model_validate(user))


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
    return ApiResponse(data=AdminUserResponse.model_validate(user))


# ── Account security (PRR 6.1 session governance) ────────────────────────────


@admin_router.get(
    "/users/{user_id}/sessions",
    response_model=ApiResponse[list[SessionInfo]],
    dependencies=SUPER_ADMIN_ONLY,
)
async def list_user_sessions(
    user_id: uuid.UUID,
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[list[SessionInfo]]:
    sessions = await service.list_user_sessions(user_id)
    return ApiResponse(data=[SessionInfo.model_validate(s) for s in sessions])


@admin_router.delete(
    "/users/{user_id}/sessions",
    response_model=ApiResponse[None],
    dependencies=SUPER_ADMIN_ONLY,
)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[None]:
    await service.revoke_user_sessions(
        user_id,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(message="All sessions revoked.")


@admin_router.post(
    "/users/{user_id}/mfa/reset",
    response_model=ApiResponse[AdminUserResponse],
    dependencies=SUPER_ADMIN_ONLY,
)
async def reset_user_mfa(
    user_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[AdminUserResponse]:
    user = await service.reset_user_mfa(
        user_id,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ApiResponse(
        data=AdminUserResponse.model_validate(user),
        message="MFA reset. The user enrolls a new authenticator at next sign-in.",
    )


@admin_router.post(
    "/users/{user_id}/password-reset",
    response_model=ApiResponse[None],
    dependencies=SUPER_ADMIN_ONLY,
)
async def send_user_password_reset(
    user_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    user = await service.get_user(user_id)
    ctx = RequestContext(
        ip_address=resolve_client_ip(request), user_agent=request.headers.get("user-agent")
    )
    raw_token = await auth_service.request_password_reset(email=user.email, ctx=ctx)
    if raw_token is not None:
        await OutboxService.enqueue_job(
            db,
            "send_password_reset_email_job",
            to=user.email,
            reset_url=_build_reset_url(raw_token, ClientType.MOBILE.value),
        )
    await AuditService(db).record(
        event_type=AuthAuditEventType.ADMIN_PASSWORD_RESET_SENT,
        actor_id=current_user.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        metadata={"user_id": str(user.id), "email": user.email},
    )
    return ApiResponse(message=f"Password reset link sent to {user.email}.")


# ── User-level permission overrides ──────────────────────────────────────────


@admin_router.get(
    "/users/{user_id}/permissions",
    response_model=ApiResponse[list[str]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def list_user_direct_permissions(
    user_id: uuid.UUID,
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[list[str]]:
    """List all direct permission overrides for a user (not from roles)."""
    codes = await service.list_user_permissions(user_id)
    return ApiResponse(data=codes)


@admin_router.post(
    "/users/{user_id}/permissions",
    response_model=ApiResponse[list[str]],
    dependencies=SUPER_ADMIN_ONLY,
)
async def grant_user_direct_permissions(
    user_id: uuid.UUID,
    payload: UserPermissionGrantRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[list[str]]:
    """Grant direct permission overrides to a user (supplements role permissions)."""
    codes = await service.grant_user_permissions(
        user_id,
        payload.permission_codes,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(data=codes, message="Permissions granted.")


@admin_router.delete(
    "/users/{user_id}/permissions/{permission_code}",
    response_model=ApiResponse[bool],
    dependencies=SUPER_ADMIN_ONLY,
)
async def revoke_user_direct_permission(
    user_id: uuid.UUID,
    permission_code: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdminService = Depends(_get_admin_service),
) -> ApiResponse[bool]:
    """Revoke a single direct permission override from a user."""
    revoked = await service.revoke_user_permission(
        user_id,
        permission_code,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=revoked, message="Permission revoked." if revoked else "Permission not found."
    )
