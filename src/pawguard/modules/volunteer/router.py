"""API router for the Volunteer Management module.

Routers only validate and call services (RULE-004).
"""

import uuid
from typing import Annotated

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
from pawguard.modules.storage.schemas import DownloadUrlResponse
from pawguard.modules.volunteer.models import VolunteerStatus
from pawguard.modules.volunteer.repository import VolunteerRepository
from pawguard.modules.volunteer.schemas import (
    ShiftAttendanceResponse,
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

router = APIRouter(prefix="/volunteers", tags=["volunteers"])


def get_volunteer_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> VolunteerService:
    repo = VolunteerRepository(db)
    return VolunteerService(repo, audit_service=audit)


@router.post(
    "/apply",
    response_model=ApiResponse[VolunteerProfileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def apply_to_volunteer(
    payload: VolunteerProfileCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(rate_limit("volunteer_apply", 5, 3600))] = None,
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerProfileResponse]:
    ip = request.client.host if request.client else None
    profile = await service.apply_to_volunteer(
        current_user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=VolunteerProfileResponse.model_validate(profile),
        message="Volunteer application submitted successfully.",
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
@router.delete(
    "/admin/volunteers/{profile_id}",
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
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[ShiftAttendanceResponse]:
    attendance = await service.check_in(attendance_id, current_user.id)
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
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[ShiftAttendanceResponse]:
    attendance = await service.check_out(attendance_id, current_user.id)
    return ApiResponse(
        data=ShiftAttendanceResponse.model_validate(attendance),
        message="Checked out from shift.",
    )


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
    dependencies=[Depends(require_permission("volunteer:update"))],
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


@router.delete(
    "/{profile_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("volunteer:update"))],
)
async def soft_delete_profile(
    profile_id: uuid.UUID,
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[None]:
    await service.soft_delete_profile(profile_id)
    return ApiResponse(message="Volunteer profile deleted.")


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
