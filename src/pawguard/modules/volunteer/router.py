"""API router for the Volunteer Management module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import get_current_user, CurrentUser
from pawguard.modules.auth.models import User
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
    response_model=ApiResponse[list[VolunteerShiftResponse]],
    dependencies=[Depends(require_permission("public:read"))],
)
async def list_shifts(
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[list[VolunteerShiftResponse]]:
    shifts = await service.list_shifts()
    return ApiResponse(data=[VolunteerShiftResponse.model_validate(s) for s in shifts])


@router.get(
    "",
    response_model=ApiResponse[list[VolunteerProfileResponse]],
    dependencies=[Depends(require_permission("volunteer:read"))],
)
async def list_profiles(
    status: VolunteerStatus | None = None,
    service: VolunteerService = Depends(get_volunteer_service),
) -> ApiResponse[list[VolunteerProfileResponse]]:
    profiles = await service.list_profiles(status)
    return ApiResponse(data=[VolunteerProfileResponse.model_validate(p) for p in profiles])
