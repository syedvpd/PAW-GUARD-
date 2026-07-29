"""API router for the Foster Management module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import get_current_user, CurrentUser
from pawguard.modules.auth.models import User
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.foster.models import FosterStatus
from pawguard.modules.foster.repository import FosterRepository
from pawguard.modules.foster.schemas import (
    FosterPlacementCreate,
    FosterPlacementResponse,
    FosterProfileCreate,
    FosterProfileResponse,
    FosterProfileUpdate,
    FosterReturnRequest,
)
from pawguard.modules.foster.service import FosterService

router = APIRouter(prefix="/fosters", tags=["fosters"])


def get_foster_service(db: AsyncSession = Depends(get_db)) -> FosterService:
    repo = FosterRepository(db)
    dog_repo = DogRepository(db)
    return FosterService(repo, dog_repo)


@router.post(
    "/apply",
    response_model=ApiResponse[FosterProfileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def apply_to_foster(
    payload: FosterProfileCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    profile = await service.apply_to_foster(current_user.id, payload)
    return ApiResponse(
        data=FosterProfileResponse.model_validate(profile),
        message="Foster application submitted successfully.",
    )


@router.put(
    "/{profile_id}",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:update"))],
)
async def update_profile(
    profile_id: uuid.UUID,
    payload: FosterProfileUpdate,
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    profile = await service.update_profile(profile_id, payload)
    return ApiResponse(
        data=FosterProfileResponse.model_validate(profile),
        message="Foster profile updated successfully.",
    )


@router.post(
    "/{profile_id}/placements",
    response_model=ApiResponse[FosterPlacementResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("foster:approve"))],
)
async def place_dog(
    profile_id: uuid.UUID,
    payload: FosterPlacementCreate,
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterPlacementResponse]:
    placement = await service.place_dog(profile_id, payload)
    return ApiResponse(
        data=FosterPlacementResponse.model_validate(placement),
        message="Dog placed in foster home successfully.",
    )


@router.post(
    "/placements/{placement_id}/return",
    response_model=ApiResponse[FosterPlacementResponse],
    dependencies=[Depends(require_permission("foster:approve"))],
)
async def return_dog(
    placement_id: uuid.UUID,
    payload: FosterReturnRequest,
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterPlacementResponse]:
    placement = await service.return_dog(placement_id, notes=payload.notes)
    return ApiResponse(
        data=FosterPlacementResponse.model_validate(placement),
        message="Dog returned to shelter facility.",
    )


@router.get(
    "",
    response_model=ApiResponse[list[FosterProfileResponse]],
    dependencies=[Depends(require_permission("foster:read"))],
)
async def list_profiles(
    status: FosterStatus | None = None,
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[list[FosterProfileResponse]]:
    profiles = await service.list_profiles(status)
    return ApiResponse(data=[FosterProfileResponse.model_validate(p) for p in profiles])
