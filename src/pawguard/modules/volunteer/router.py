"""API router for the Volunteer Management module.

Routers only validate and call services (RULE-004).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.exceptions import ForbiddenError, parse_enum
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.rate_limiter import rate_limit
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import has_permission, require_permission
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.storage.schemas import DownloadUrlResponse
from pawguard.modules.volunteer.models import ApplicationStatus, VolunteerStatus
from pawguard.modules.volunteer.repository import VolunteerRepository
from pawguard.modules.volunteer.schemas import (
    ShiftAttendanceCancel,
    ShiftAttendanceNoShow,
    ShiftAttendanceResponse,
    VolunteerApplicationReject,
    VolunteerApplicationResponse,
    VolunteerLifecycleStatus,
    VolunteerProfileCreate,
    VolunteerProfileResponse,
    VolunteerProfileUpdate,
    VolunteerServiceSummary,
    VolunteerShiftCreate,
    VolunteerShiftResponse,
)
from pawguard.modules.volunteer.service import VolunteerService
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/volunteers", tags=["volunteers"])


def get_volunteer_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    arq_pool: Any = Depends(get_arq_pool),
) -> VolunteerService:
    repo = VolunteerRepository(db)
    notification_repo = NotificationRepository(db)
    notification_svc = NotificationService(repository=notification_repo, arq_pool=arq_pool)
    return VolunteerService(repo, audit_service=audit, notification_service=notification_svc)


@router.post(
    "/apply",
    response_model=ApiResponse[VolunteerApplicationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def apply_to_volunteer(
    payload: VolunteerProfileCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(rate_limit("volunteer_apply", 5, 3600))] = None,
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerApplicationResponse]:
    ip = request.client.host if request.client else None
    application = await service.apply_to_volunteer(
        current_user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=VolunteerApplicationResponse.model_validate(application),
        message="Volunteer application submitted successfully.",
    )


@router.get(
    "/me/status",
    response_model=ApiResponse[VolunteerLifecycleStatus],
)
async def get_my_volunteer_status(
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerLifecycleStatus]:
    """Get the current user's volunteer lifecycle status."""
    status_data = await service.get_volunteer_lifecycle_status(current_user.id)
    return ApiResponse(data=status_data)


@router.get(
    "/me/application",
    response_model=ApiResponse[VolunteerApplicationResponse | None],
)
async def get_my_application(
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerApplicationResponse | None]:
    """Get the current user's volunteer application if it exists."""
    application = await service.get_application_by_user(current_user.id)
    if application is None:
        return ApiResponse(data=None, message="No application found.")
    return ApiResponse(data=VolunteerApplicationResponse.model_validate(application))


@router.get(
    "/applications",
    response_model=PaginatedResponse[VolunteerApplicationResponse],
    dependencies=[Depends(require_permission("volunteer:read"))],
)
async def list_applications(
    params: PageParams = Depends(page_params),
    status: ApplicationStatus | None = Query(None, description="Filter by application status"),
    service: VolunteerService = Depends(get_volunteer_service),
) -> PaginatedResponse[VolunteerApplicationResponse]:
    """Coordinator review queue: applications submitted via POST /apply,
    not yet promoted to a VolunteerProfile by approve/reject."""
    applications, meta = await service.list_applications(page_params=params, status=status)
    return PaginatedResponse(
        data=[VolunteerApplicationResponse.model_validate(a) for a in applications],
        meta=meta,
    )


@router.post(
    "/applications/{application_id}/approve",
    response_model=ApiResponse[VolunteerProfileResponse],
    dependencies=[Depends(require_permission("volunteer:update"))],
)
async def approve_application(
    application_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerProfileResponse]:
    """Approve a volunteer application and create a volunteer profile."""
    ip = request.client.host if request.client else None
    profile = await service.approve_application(
        application_id,
        current_user.id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=VolunteerProfileResponse.model_validate(profile),
        message="Volunteer application approved.",
    )


@router.post(
    "/applications/{application_id}/reject",
    response_model=ApiResponse[VolunteerApplicationResponse],
    dependencies=[Depends(require_permission("volunteer:update"))],
)
async def reject_application(
    application_id: uuid.UUID,
    payload: VolunteerApplicationReject,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerApplicationResponse]:
    """Reject a volunteer application."""
    ip = request.client.host if request.client else None
    application = await service.reject_application(
        application_id,
        current_user.id,
        payload.reason,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=VolunteerApplicationResponse.model_validate(application),
        message="Volunteer application rejected.",
    )


@router.put(
    "/{profile_id}",
    response_model=ApiResponse[VolunteerProfileResponse],
    dependencies=[Depends(require_permission("volunteer:update"))],
)
async def update_profile(
    profile_id: uuid.UUID,
    payload: VolunteerProfileUpdate,
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerProfileResponse]:
    profile = await service.update_profile(profile_id, payload)
    return ApiResponse(
        data=VolunteerProfileResponse.model_validate(profile),
        message="Volunteer profile updated successfully.",
    )


@router.delete(
    "/{profile_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("volunteer:update"))],
)
async def soft_delete_profile(
    profile_id: uuid.UUID,
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[None]:
    await service.soft_delete_profile(profile_id)
    return ApiResponse(message="Volunteer profile deleted successfully.")


@router.get(
    "/shifts",
    response_model=PaginatedResponse[VolunteerShiftResponse],
    dependencies=[Depends(require_permission("public:read"))],
)
async def list_shifts(
    params: PageParams = Depends(page_params),
    role_name: str | None = Query(None, description="Filter by shift role"),
    sort: SortParams = Depends(sort_params),
    service: VolunteerService = Depends(get_volunteer_service),
) -> PaginatedResponse[VolunteerShiftResponse]:
    shifts, meta = await service.list_shifts(page_params=params, role_name=role_name, sort=sort)
    return PaginatedResponse(
        data=[VolunteerShiftResponse.model_validate(s) for s in shifts],
        meta=meta,
    )


@router.get(
    "/{profile_id}",
    response_model=ApiResponse[VolunteerProfileResponse],
)
async def get_profile(
    profile_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerProfileResponse]:
    profile = await service.get_profile(profile_id)
    is_owner = profile.user_id == current_user.user.id
    if not is_owner and not has_permission(current_user.user, "volunteer:update"):
        raise ForbiddenError("You do not have permission to view this volunteer profile.")
    return ApiResponse(data=VolunteerProfileResponse.model_validate(profile))


@router.post(
    "/shifts",
    response_model=ApiResponse[VolunteerShiftResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("volunteer:schedule"))],
)
async def create_shift(
    payload: VolunteerShiftCreate,
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerShiftResponse]:
    shift = await service.create_shift(payload)
    return ApiResponse(
        data=VolunteerShiftResponse.model_validate(shift),
        message="Volunteer shift created successfully.",
    )


@router.post(
    "/shifts/{shift_id}/join",
    response_model=ApiResponse[ShiftAttendanceResponse],
)
async def join_shift(
    shift_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[ShiftAttendanceResponse]:
    profile = await service.get_profile_by_user(current_user.id)
    if profile is None:
        from pawguard.core.exceptions import NotFoundError

        raise NotFoundError("Volunteer profile not found. Please apply to volunteer first.")
    attendance = await service.join_shift(shift_id, profile.id)
    return ApiResponse(
        data=ShiftAttendanceResponse.model_validate(attendance),
        message="Joined volunteer shift successfully.",
    )


@router.post(
    "/attendance/{attendance_id}/check-in",
    response_model=ApiResponse[ShiftAttendanceResponse],
)
async def check_in(
    attendance_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[ShiftAttendanceResponse]:
    ip = request.client.host if request.client else None
    attendance = await service.check_in(attendance_id, current_user.user, ip_address=ip)
    return ApiResponse(
        data=ShiftAttendanceResponse.model_validate(attendance),
        message="Checked in for shift.",
    )


@router.post(
    "/attendance/{attendance_id}/check-out",
    response_model=ApiResponse[ShiftAttendanceResponse],
)
async def check_out(
    attendance_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[ShiftAttendanceResponse]:
    ip = request.client.host if request.client else None
    attendance = await service.check_out(attendance_id, current_user.user, ip_address=ip)
    return ApiResponse(
        data=ShiftAttendanceResponse.model_validate(attendance),
        message="Checked out from shift.",
    )


@router.post(
    "/attendance/{attendance_id}/no-show",
    response_model=ApiResponse[ShiftAttendanceResponse],
)
async def mark_no_show(
    attendance_id: uuid.UUID,
    payload: ShiftAttendanceNoShow,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[ShiftAttendanceResponse]:
    ip = request.client.host if request.client else None
    attendance = await service.mark_no_show(
        attendance_id, current_user.user, payload.reason, ip_address=ip
    )
    return ApiResponse(
        data=ShiftAttendanceResponse.model_validate(attendance),
        message="Volunteer marked as a no-show.",
    )


@router.post(
    "/attendance/{attendance_id}/cancel",
    response_model=ApiResponse[ShiftAttendanceResponse],
)
async def cancel_attendance(
    attendance_id: uuid.UUID,
    payload: ShiftAttendanceCancel,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[ShiftAttendanceResponse]:
    ip = request.client.host if request.client else None
    attendance = await service.cancel_attendance(
        attendance_id, current_user.user, payload.reason, ip_address=ip
    )
    return ApiResponse(
        data=ShiftAttendanceResponse.model_validate(attendance),
        message="Shift claim cancelled.",
    )


@router.get(
    "/shifts/{shift_id}/attendance",
    response_model=PaginatedResponse[ShiftAttendanceResponse],
    dependencies=[Depends(require_permission("volunteer:read"))],
)
async def list_shift_attendance(
    shift_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    service: VolunteerService = Depends(get_volunteer_service),
) -> PaginatedResponse[ShiftAttendanceResponse]:
    records, meta = await service.list_attendance(shift_id, page_params=params)
    return PaginatedResponse(
        data=[ShiftAttendanceResponse.model_validate(r) for r in records],
        meta=meta,
    )


@router.get(
    "",
    response_model=PaginatedResponse[VolunteerProfileResponse],
    dependencies=[Depends(require_permission("volunteer:read"))],
)
async def list_profiles(
    params: PageParams = Depends(page_params),
    status: VolunteerStatus | None = Query(None, description="Filter by volunteer status"),
    search: str | None = Query(None, description="Search by skills or availability"),
    sort: SortParams = Depends(sort_params),
    service: VolunteerService = Depends(get_volunteer_service),
) -> PaginatedResponse[VolunteerProfileResponse]:
    profiles, meta = await service.list_profiles(
        page_params=params,
        status=status,
        search=search,
        sort=sort,
    )
    return PaginatedResponse(
        data=[VolunteerProfileResponse.model_validate(p) for p in profiles],
        meta=meta,
    )


@router.post(
    "/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("volunteer:update"))],
)
async def bulk_delete_profiles(
    payload: BulkDeleteRequest,
    service: VolunteerService = Depends(get_volunteer_service),
) -> BulkDeleteResponse:
    deleted = await service.bulk_delete_profiles(payload.ids)
    return BulkDeleteResponse(
        message=f"{deleted} volunteer profile(s) deleted.",
        deleted_count=deleted,
    )


@router.get(
    "/{profile_id}/certificate",
    response_model=ApiResponse[DownloadUrlResponse],
)
async def issue_service_certificate(
    profile_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[DownloadUrlResponse]:
    """Generate a verified service certificate (PDF) for a volunteer based on
    attended shifts (PRR 3.9). The volunteer themself or staff may request it."""
    profile = await service.get_profile(profile_id)
    is_owner = profile.user_id == current_user.user.id
    if not is_owner and not has_permission(current_user.user, "volunteer:update"):
        raise ForbiddenError("You do not have permission to issue this certificate.")

    ip = request.client.host if request.client else None
    _, object_key = await service.issue_service_certificate(
        profile_id,
        actor_id=current_user.id,
        ip_address=ip,
        storage_service=StorageService(),
    )
    if not object_key:
        raise ForbiddenError("Certificate storage is not configured; try again later.")

    storage = StorageService()
    download_url = storage.generate_presigned_download_url(object_key=object_key)
    return ApiResponse(
        data=DownloadUrlResponse(
            download_url=download_url,
            object_key=object_key,
            file_id=profile_id,
        ),
        message="Volunteer service certificate generated.",
    )


@router.get(
    "/{profile_id}/service-summary",
    response_model=ApiResponse[VolunteerServiceSummary],
)
async def get_service_summary(
    profile_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerServiceSummary]:
    profile = await service.get_profile(profile_id)
    is_owner = profile.user_id == current_user.user.id
    if not is_owner and not has_permission(current_user.user, "volunteer:update"):
        raise ForbiddenError("You do not have permission to view this service summary.")
    return ApiResponse(data=await service.get_service_summary(profile_id))


@router.post(
    "/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("volunteer:update"))],
)
async def bulk_update_profile_status(
    payload: BulkStatusUpdateRequest,
    service: VolunteerService = Depends(get_volunteer_service),
) -> BulkStatusUpdateResponse:
    status = parse_enum(VolunteerStatus, payload.status)
    updated = await service.bulk_update_profile_status(payload.ids, status)
    return BulkStatusUpdateResponse(
        message=f"{updated} volunteer profile(s) updated.",
        updated_count=updated,
    )
