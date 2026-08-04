"""API router for Rescue Centres management (/api/v1/rescue-centres).

Provides endpoints for managing Rescue Centres / Shelter Facilities and returning
active counts for Super Admin Dashboard.
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
from pawguard.core.exceptions import parse_enum
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import (
    CurrentUser,
    get_current_user,
    get_optional_current_user,
)
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.service import InventoryService
from pawguard.modules.shelter.models import FacilityStatus, FacilityType
from pawguard.modules.shelter.repository import ShelterRepository
from pawguard.modules.shelter.schemas import (
    FacilityStatusUpdate,
    ShelterFacilityCreate,
    ShelterFacilityResponse,
    ShelterFacilityUpdate,
)
from pawguard.modules.shelter.service import ShelterService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/rescue-centres", tags=["rescue-centres"])


def get_shelter_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> ShelterService:
    repo = ShelterRepository(db)
    dog_repo = DogRepository(db)
    inventory = InventoryService(InventoryRepository(db), audit_service=audit)
    return ShelterService(repo, dog_repo, audit_service=audit, inventory_service=inventory)


@router.get(
    "",
    response_model=PaginatedResponse[ShelterFacilityResponse],
)
async def list_rescue_centres(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    status: FacilityStatus | None = None,
    facility_type: FacilityType | None = None,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
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
        data=[ShelterFacilityResponse.model_validate(f) for f in result.data],
        meta=result.meta,
    )


@router.post(
    "",
    response_model=ApiResponse[ShelterFacilityResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_rescue_centre(
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
        message="Rescue Centre created successfully.",
    )


@router.get(
    "/{facility_id}",
    response_model=ApiResponse[ShelterFacilityResponse],
)
async def get_rescue_centre(
    facility_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.get_facility(facility_id)
    return ApiResponse(data=ShelterFacilityResponse.model_validate(facility))


@router.put(
    "/{facility_id}",
    response_model=ApiResponse[ShelterFacilityResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_rescue_centre(
    facility_id: uuid.UUID,
    payload: ShelterFacilityUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.update_facility(
        facility_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ShelterFacilityResponse.model_validate(facility),
        message="Rescue Centre updated successfully.",
    )


@router.delete(
    "/{facility_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def delete_rescue_centre(
    facility_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[None]:
    await service.soft_delete_facility(facility_id)
    return ApiResponse(message="Rescue Centre deleted successfully.")


@router.put(
    "/{facility_id}/status",
    response_model=ApiResponse[ShelterFacilityResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_rescue_centre_status(
    facility_id: uuid.UUID,
    payload: FacilityStatusUpdate,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.update_facility_status(
        facility_id, payload.status,
    )
    return ApiResponse(
        data=ShelterFacilityResponse.model_validate(facility),
        message="Rescue Centre status updated.",
    )


@router.post(
    "/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_delete_rescue_centres(
    payload: BulkDeleteRequest,
    service: ShelterService = Depends(get_shelter_service),
) -> BulkDeleteResponse:
    deleted = await service.bulk_delete_facilities(
        payload.ids,
    )
    return BulkDeleteResponse(
        message=f"{deleted} rescue centres deleted.",
        deleted_count=deleted,
    )


@router.post(
    "/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_update_rescue_centre_status(
    payload: BulkStatusUpdateRequest,
    service: ShelterService = Depends(get_shelter_service),
) -> BulkStatusUpdateResponse:
    updated = await service.bulk_update_facility_status(
        payload.ids, parse_enum(FacilityStatus, payload.status),
    )
    return BulkStatusUpdateResponse(
        message=f"{updated} rescue centres updated.",
        updated_count=updated,
    )
