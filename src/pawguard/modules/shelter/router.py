"""Shelter & Capacity API router.

Routers only validate and call services (RULE-004).
"""

import uuid

from fastapi import APIRouter, Depends, Request, status
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
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.shelter.models import (
    FacilityStatus,
    FacilityType,
    KennelSanitationState,
)
from pawguard.modules.shelter.repository import ShelterRepository
from pawguard.modules.shelter.schemas import (
    DailyCareLogCreate,
    DailyCareLogResponse,
    FacilityStatusUpdate,
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
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/shelter", tags=["shelter"])


def get_shelter_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> ShelterService:
    repo = ShelterRepository(db)
    dog_repo = DogRepository(db)
    return ShelterService(repo, dog_repo, audit_service=audit)


@router.post(
    "/facilities",
    response_model=ApiResponse[ShelterFacilityResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_facility(
    payload: ShelterFacilityCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.create_facility(
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ShelterFacilityResponse.model_validate(facility),
        message="Shelter facility created successfully.",
    )


@router.get(
    "/facilities",
    response_model=PaginatedResponse[ShelterFacilityResponse],
)
async def list_facilities(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    status: FacilityStatus | None = None,
    facility_type: FacilityType | None = None,
    service: ShelterService = Depends(get_shelter_service),
) -> PaginatedResponse[ShelterFacilityResponse]:
    result = await service.list_facilities_paginated(
        page,
        sort,
        search_term=search,
        status=status,
        facility_type=facility_type,
    )
    return PaginatedResponse(
        data=[
            ShelterFacilityResponse.model_validate(f)
            for f in result.data
        ],
        meta=result.meta,
    )


@router.post(
    "/facilities/{facility_id}/sections",
    response_model=ApiResponse[ShelterSectionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_section(
    facility_id: uuid.UUID,
    payload: ShelterSectionCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterSectionResponse]:
    section = await service.create_section(
        facility_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ShelterSectionResponse.model_validate(section),
        message="Shelter section created successfully.",
    )


@router.get(
    "/facilities/{facility_id}/sections",
    response_model=PaginatedResponse[ShelterSectionResponse],
)
async def list_sections(
    facility_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    service: ShelterService = Depends(get_shelter_service),
) -> PaginatedResponse[ShelterSectionResponse]:
    result = await service.list_sections_paginated(
        page,
        sort,
        facility_id=facility_id,
        search_term=search,
    )
    return PaginatedResponse(
        data=[
            ShelterSectionResponse.model_validate(s)
            for s in result.data
        ],
        meta=result.meta,
    )


@router.post(
    "/sections/{section_id}/kennels",
    response_model=ApiResponse[KennelResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_kennel(
    section_id: uuid.UUID,
    payload: KennelCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[KennelResponse]:
    kennel = await service.create_kennel(
        section_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=KennelResponse.model_validate(kennel),
        message="Kennel created successfully.",
    )


@router.get(
    "/sections/{section_id}/kennels",
    response_model=PaginatedResponse[KennelResponse],
)
async def list_kennels(
    section_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    service: ShelterService = Depends(get_shelter_service),
) -> PaginatedResponse[KennelResponse]:
    result = await service.list_kennels_paginated(
        page, sort, section_id=section_id,
    )
    return PaginatedResponse(
        data=[
            KennelResponse.model_validate(k)
            for k in result.data
        ],
        meta=result.meta,
    )


@router.post(
    "/kennels/{kennel_id}/assign/{dog_id}",
    response_model=ApiResponse[bool],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def assign_dog_to_kennel(
    kennel_id: uuid.UUID,
    dog_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[bool]:
    success = await service.assign_dog_to_kennel(
        dog_id,
        kennel_id,
        actor_id=current_user.id,
        ip_address=request.client.host
        if request.client
        else None,
    )
    return ApiResponse(
        data=success,
        message="Dog successfully assigned to kennel.",
    )


@router.put(
    "/kennels/{kennel_id}/sanitation",
    response_model=ApiResponse[KennelResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_kennel_sanitation(
    kennel_id: uuid.UUID,
    status_val: KennelSanitationState,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[KennelResponse]:
    kennel = await service.update_kennel_sanitation(
        kennel_id,
        status_val,
        actor_id=current_user.id,
        ip_address=request.client.host
        if request.client
        else None,
    )
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
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[FacilityTransferResponse]:
    transfer = await service.request_transfer(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host
        if request.client
        else None,
    )
    return ApiResponse(
        data=FacilityTransferResponse.model_validate(transfer),
        message=(
            "Inter-facility transfer request submitted "
            "successfully."
        ),
    )


@router.post(
    "/transfers/{transfer_id}/confirm",
    response_model=ApiResponse[FacilityTransferResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def confirm_transfer(
    transfer_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[FacilityTransferResponse]:
    transfer = await service.confirm_transfer(
        transfer_id,
        actor_id=current_user.id,
        ip_address=request.client.host
        if request.client
        else None,
    )
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
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[DailyCareLogResponse]:
    care_log = await service.submit_daily_care_log(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host
        if request.client
        else None,
    )
    return ApiResponse(
        data=DailyCareLogResponse.model_validate(care_log),
        message=(
            "Daily care operational updates recorded "
            "successfully."
        ),
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
    return ApiResponse(
        data=[
            DailyCareLogResponse.model_validate(log)
            for log in logs
        ],
    )


@router.delete(
    "/facilities/{facility_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def delete_facility(
    facility_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[None]:
    await service.soft_delete_facility(facility_id)
    return ApiResponse(message="Shelter facility deleted.")


@router.put(
    "/facilities/{facility_id}/status",
    response_model=ApiResponse[ShelterFacilityResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_facility_status(
    facility_id: uuid.UUID,
    payload: FacilityStatusUpdate,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.update_facility_status(
        facility_id, payload.status,
    )
    return ApiResponse(
        data=ShelterFacilityResponse.model_validate(facility),
        message="Facility status updated.",
    )


@router.post(
    "/facilities/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_delete_facilities(
    payload: BulkDeleteRequest,
    service: ShelterService = Depends(get_shelter_service),
) -> BulkDeleteResponse:
    deleted = await service.bulk_delete_facilities(
        payload.ids,
    )
    return BulkDeleteResponse(
        message=f"{deleted} facilities deleted.",
        deleted_count=deleted,
    )


@router.post(
    "/facilities/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_update_facility_status(
    payload: BulkStatusUpdateRequest,
    service: ShelterService = Depends(get_shelter_service),
) -> BulkStatusUpdateResponse:
    updated = await service.bulk_update_facility_status(
        payload.ids, FacilityStatus(payload.status),
    )
    return BulkStatusUpdateResponse(
        message=f"{updated} facilities updated.",
        updated_count=updated,
    )
