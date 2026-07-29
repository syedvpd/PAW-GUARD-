"""API router for the Shelter & Capacity module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Sequence
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import get_current_user, CurrentUser
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.shelter.models import KennelSanitationState
from pawguard.modules.shelter.repository import ShelterRepository
from pawguard.modules.shelter.schemas import (
    DailyCareLogCreate,
    DailyCareLogResponse,
    FacilityTransferCreate,
    FacilityTransferResponse,
    KennelCreate,
    KennelResponse,
    ShelterFacilityCreate,
    ShelterFacilityResponse,
    ShelterSectionCreate,
    ShelterSectionResponse,
)
from pawguard.modules.shelter.service import ShelterService

router = APIRouter(prefix="/shelter", tags=["shelter"])


def get_shelter_service(db: AsyncSession = Depends(get_db)) -> ShelterService:
    repo = ShelterRepository(db)
    dog_repo = DogRepository(db)
    return ShelterService(repo, dog_repo)


@router.post(
    "/facilities",
    response_model=ApiResponse[ShelterFacilityResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_facility(
    payload: ShelterFacilityCreate,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.create_facility(payload)
    return ApiResponse(
        data=ShelterFacilityResponse.model_validate(facility),
        message="Shelter facility created successfully.",
    )


@router.get(
    "/facilities",
    response_model=ApiResponse[list[ShelterFacilityResponse]],
)
async def list_facilities(
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[list[ShelterFacilityResponse]]:
    facilities = await service.list_facilities()
    return ApiResponse(data=[ShelterFacilityResponse.model_validate(f) for f in facilities])


@router.post(
    "/facilities/{facility_id}/sections",
    response_model=ApiResponse[ShelterSectionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_section(
    facility_id: uuid.UUID,
    payload: ShelterSectionCreate,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterSectionResponse]:
    section = await service.create_section(facility_id, payload)
    return ApiResponse(
        data=ShelterSectionResponse.model_validate(section),
        message="Shelter section created successfully.",
    )


@router.get(
    "/facilities/{facility_id}/sections",
    response_model=ApiResponse[list[ShelterSectionResponse]],
)
async def list_sections(
    facility_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[list[ShelterSectionResponse]]:
    sections = await service.list_sections(facility_id)
    return ApiResponse(data=[ShelterSectionResponse.model_validate(s) for s in sections])


@router.post(
    "/sections/{section_id}/kennels",
    response_model=ApiResponse[KennelResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_kennel(
    section_id: uuid.UUID,
    payload: KennelCreate,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[KennelResponse]:
    kennel = await service.create_kennel(section_id, payload)
    return ApiResponse(
        data=KennelResponse.model_validate(kennel),
        message="Kennel created successfully.",
    )


@router.get(
    "/sections/{section_id}/kennels",
    response_model=ApiResponse[list[KennelResponse]],
)
async def list_kennels(
    section_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[list[KennelResponse]]:
    kennels = await service.list_kennels(section_id)
    return ApiResponse(data=[KennelResponse.model_validate(k) for k in kennels])


@router.post(
    "/kennels/{kennel_id}/assign/{dog_id}",
    response_model=ApiResponse[bool],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def assign_dog_to_kennel(
    kennel_id: uuid.UUID,
    dog_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[bool]:
    success = await service.assign_dog_to_kennel(dog_id, kennel_id)
    return ApiResponse(data=success, message="Dog successfully assigned to kennel.")


@router.put(
    "/kennels/{kennel_id}/sanitation",
    response_model=ApiResponse[KennelResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_kennel_sanitation(
    kennel_id: uuid.UUID,
    status_val: KennelSanitationState,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[KennelResponse]:
    kennel = await service.update_kennel_sanitation(kennel_id, status_val)
    return ApiResponse(
        data=KennelResponse.model_validate(kennel),
        message="Kennel sanitation status updated successfully.",
    )


@router.post(
    "/transfers",
    response_model=ApiResponse[FacilityTransferResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def request_transfer(
    payload: FacilityTransferCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[FacilityTransferResponse]:
    transfer = await service.request_transfer(current_user.user.id, payload)
    return ApiResponse(
        data=FacilityTransferResponse.model_validate(transfer),
        message="Inter-facility transfer request submitted successfully.",
    )


@router.post(
    "/transfers/{transfer_id}/confirm",
    response_model=ApiResponse[FacilityTransferResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def confirm_transfer(
    transfer_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[FacilityTransferResponse]:
    transfer = await service.confirm_transfer(transfer_id)
    return ApiResponse(
        data=FacilityTransferResponse.model_validate(transfer),
        message="Inter-facility transfer confirmation recorded.",
    )


@router.post(
    "/care-logs",
    response_model=ApiResponse[DailyCareLogResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def submit_daily_care_log(
    payload: DailyCareLogCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[DailyCareLogResponse]:
    care_log = await service.submit_daily_care_log(current_user.user.id, payload)
    return ApiResponse(
        data=DailyCareLogResponse.model_validate(care_log),
        message="Daily care operational updates recorded successfully.",
    )


@router.get(
    "/dogs/{dog_id}/care-logs",
    response_model=ApiResponse[list[DailyCareLogResponse]],
)
async def list_care_logs(
    dog_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[list[DailyCareLogResponse]]:
    logs = await service.list_care_logs(dog_id)
    return ApiResponse(data=[DailyCareLogResponse.model_validate(l) for l in logs])
