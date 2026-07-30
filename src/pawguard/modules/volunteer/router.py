"""API router for the Volunteer Management module. Routers only validate and call services (RULE-004)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.volunteer.models import VolunteerStatus
from pawguard.modules.volunteer.repository import VolunteerRepository
from pawguard.modules.volunteer.schemas import (
    ShiftAttendanceResponse,
    VolunteerProfileCreate,
    VolunteerProfileResponse,
    VolunteerProfileUpdate,
    VolunteerShiftCreate,
    VolunteerShiftResponse,
)
from pawguard.modules.volunteer.service import VolunteerService

router = APIRouter(prefix="/volunteers", tags=["volunteers"])


def get_volunteer_service(db: AsyncSession = Depends(get_db)) -> VolunteerService:
    repo = VolunteerRepository(db)
    return VolunteerService(repo)


@router.post(
    "/apply",
    response_model=ApiResponse[VolunteerProfileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def apply_to_volunteer(
    payload: VolunteerProfileCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[VolunteerProfileResponse]:
    profile = await service.apply_to_volunteer(current_user.id, payload)
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
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[ShiftAttendanceResponse]:
    attendance = await service.check_in(attendance_id)
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
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[ShiftAttendanceResponse]:
    attendance = await service.check_out(attendance_id)
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


@router.post(
    "/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("volunteer:update"))],
)
async def bulk_update_profile_status(
    payload: BulkStatusUpdateRequest,
    service: VolunteerService = Depends(get_volunteer_service),
) -> BulkStatusUpdateResponse:
    status = VolunteerStatus(payload.status)
    updated = await service.bulk_update_profile_status(payload.ids, status)
    return BulkStatusUpdateResponse(
        message=f"{updated} volunteer profile(s) updated.",
        updated_count=updated,
    )
