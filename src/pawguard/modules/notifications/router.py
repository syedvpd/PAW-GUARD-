"""API router for in-app notifications (RULE-004)."""

import uuid

from arq import ArqRedis
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import BulkDeleteRequest, BulkDeleteResponse
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.auth.repository import UserRepository
from pawguard.modules.notifications.repository import (
    NotificationPreferenceRepository,
    NotificationRepository,
)
from pawguard.modules.notifications.schemas import (
    BroadcastCreate,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationResponse,
    NotificationSend,
    UnreadCountResponse,
)
from pawguard.modules.notifications.service import (
    NotificationPreferenceService,
    NotificationService,
)
from pawguard.services.audit_service import AuditService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notification_service(
    db: AsyncSession = Depends(get_db),
    arq_pool: ArqRedis = Depends(get_arq_pool),
    audit: AuditService = Depends(get_audit_service),
) -> NotificationService:
    return NotificationService(NotificationRepository(db), arq_pool=arq_pool, audit_service=audit)


def get_preference_service(db: AsyncSession = Depends(get_db)) -> NotificationPreferenceService:
    return NotificationPreferenceService(NotificationPreferenceRepository(db))


@router.get("", response_model=PaginatedResponse[NotificationResponse])
async def list_notifications(
    current_user: CurrentUser = Depends(get_current_user),
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search term for title, body, or type"),
    notification_type: str | None = Query(None, description="Filter by notification type"),
    is_read: bool | None = Query(None, description="Filter by read status"),
    service: NotificationService = Depends(get_notification_service),
) -> PaginatedResponse[NotificationResponse]:
    return await service.list_paginated(
        page=page,
        sort=sort,
        user_id=current_user.id,
        search_term=search,
        notification_type=notification_type,
        is_read=is_read,
    )


@router.get("/unread-count", response_model=ApiResponse[UnreadCountResponse])
async def unread_count(
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> ApiResponse[UnreadCountResponse]:
    count = await service.count_unread(current_user.id)
    return ApiResponse(data=UnreadCountResponse(count=count))


@router.put("/{notification_id}/read", response_model=ApiResponse[NotificationResponse])
async def mark_read(
    notification_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> ApiResponse[NotificationResponse]:
    notification = await service.mark_read(notification_id, current_user.id)
    return ApiResponse(
        data=NotificationResponse.model_validate(notification),
        message="Notification marked as read.",
    )


@router.put("/read-all", response_model=ApiResponse[None])
async def mark_all_read(
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> ApiResponse[None]:
    await service.mark_all_read(current_user.id)
    return ApiResponse(message="All notifications marked as read.")


@router.delete("/{notification_id}", response_model=ApiResponse[None])
async def delete_notification(
    notification_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> ApiResponse[None]:
    await service.delete_notification(
        notification_id, user_id=current_user.id, actor_id=current_user.id, ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(message="Notification deleted.")


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("notification:manage"))],
)
async def bulk_delete_notifications(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> ApiResponse[BulkDeleteResponse]:
    deleted = await service.bulk_delete(
        payload.ids, actor_id=current_user.id, ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} notification(s) deleted.",
            deleted_count=deleted,
        ),
    )


@router.post(
    "/send",
    response_model=ApiResponse[NotificationResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("notification:manage"))],
)
async def send_notification(
    payload: NotificationSend,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> ApiResponse[NotificationResponse]:
    user_email = None
    if payload.send_email:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(payload.user_id)
        if user is not None:
            user_email = user.email
    notification = await service.send_notification(
        payload, user_email=user_email, actor_id=current_user.id, ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=NotificationResponse.model_validate(notification),
        message="Notification sent.",
    )


@router.get("/preferences", response_model=ApiResponse[NotificationPreferenceResponse])
async def get_preferences(
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationPreferenceService = Depends(get_preference_service),
) -> ApiResponse[NotificationPreferenceResponse]:
    prefs = await service.get_preferences(current_user.id)
    return ApiResponse(data=NotificationPreferenceResponse.model_validate(prefs))


@router.put("/preferences", response_model=ApiResponse[NotificationPreferenceResponse])
async def update_preferences(
    payload: NotificationPreferenceUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationPreferenceService = Depends(get_preference_service),
) -> ApiResponse[NotificationPreferenceResponse]:
    kwargs = payload.model_dump(exclude_unset=True)
    prefs = await service.update_preferences(current_user.id, **kwargs)
    return ApiResponse(
        data=NotificationPreferenceResponse.model_validate(prefs),
        message="Preferences updated.",
    )


@router.post(
    "/broadcast",
    response_model=ApiResponse[list[NotificationResponse]],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def broadcast_notification(
    payload: BroadcastCreate,
    request: Request,
    user_ids: list[uuid.UUID] = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> ApiResponse[list[NotificationResponse]]:
    notifications = await service.broadcast(
        payload, user_ids, actor_id=current_user.id, ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=[NotificationResponse.model_validate(n) for n in notifications],
        message="Broadcast sent.",
    )
