"""API router for the Foster Management module.

Routers only validate and call services (RULE-004).
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
)
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
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
    FosterProgressLogCreate,
    FosterProgressLogResponse,
    FosterReturnRequest,
    FosterSupplyDispatchCreate,
    FosterSupplyDispatchResponse,
)
from pawguard.modules.foster.service import FosterService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/fosters", tags=["fosters"])


def get_foster_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> FosterService:
    repo = FosterRepository(db)
    dog_repo = DogRepository(db)
    adoption_repo = AdoptionRepository(db)
    return FosterService(repo, dog_repo, adoption_repo=adoption_repo, audit_service=audit)


@router.post(
    "/apply",
    response_model=ApiResponse[FosterProfileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def apply_to_foster(
    payload: FosterProfileCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    ip = request.client.host if request.client else None
    profile = await service.apply_to_foster(
        current_user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
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
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    ip = request.client.host if request.client else None
    profile = await service.update_profile(
        profile_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProfileResponse.model_validate(profile),
        message="Foster profile updated successfully.",
    )


@router.delete(
    "/{profile_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("foster:update"))],
)
async def soft_delete_profile(
    profile_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_profile(
        profile_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(message="Foster profile deleted successfully.")


@router.post(
    "/{profile_id}/placements",
    response_model=ApiResponse[FosterPlacementResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("foster:approve"))],
)
async def place_dog(
    profile_id: uuid.UUID,
    payload: FosterPlacementCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterPlacementResponse]:
    ip = request.client.host if request.client else None
    placement = await service.place_dog(
        profile_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
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
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterPlacementResponse]:
    ip = request.client.host if request.client else None
    placement = await service.return_dog(
        placement_id,
        notes=payload.notes,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterPlacementResponse.model_validate(placement),
        message="Dog returned to shelter facility.",
    )


@router.get(
    "",
    response_model=PaginatedResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:read"))],
)
async def list_profiles(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by preferences, notes"),
    status: FosterStatus | None = Query(None, description="Filter by status"),
    is_available: bool | None = Query(None, description="Filter by availability"),
    service: FosterService = Depends(get_foster_service),
) -> PaginatedResponse[FosterProfileResponse]:
    return await service.list_profiles_paginated(
        page=page,
        sort=sort,
        search_term=search,
        status=status,
        is_available=is_available,
    )


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("foster:update"))],
)
async def bulk_delete_profiles(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[BulkDeleteResponse]:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_soft_delete(
        payload.ids,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} foster profile(s) deleted.",
            deleted_count=deleted,
        ),
    )


@router.post(
    "/placements/{placement_id}/progress",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("foster:approve"))],
)
async def log_progress(
    placement_id: uuid.UUID,
    payload: FosterProgressLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProgressLogResponse]:
    ip = request.client.host if request.client else None
    log = await service.log_daily_progress(
        placement_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProgressLogResponse.model_validate(log),
        message="Progress logged successfully.",
    )


@router.get(
    "/placements/{placement_id}/progress",
    response_model=ApiResponse[list[FosterProgressLogResponse]],
    dependencies=[Depends(require_permission("foster:read"))],
)
async def get_progress_logs(
    placement_id: uuid.UUID,
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[list[FosterProgressLogResponse]]:
    logs = await service.get_progress_logs(placement_id)
    return ApiResponse(
        data=[FosterProgressLogResponse.model_validate(log) for log in logs],
    )


@router.post(
    "/placements/{placement_id}/supplies",
    response_model=ApiResponse[FosterSupplyDispatchResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("foster:approve"))],
)
async def log_supply_dispatch(
    placement_id: uuid.UUID,
    payload: FosterSupplyDispatchCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterSupplyDispatchResponse]:
    ip = request.client.host if request.client else None
    dispatch = await service.log_supply_dispatch(
        placement_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterSupplyDispatchResponse.model_validate(dispatch),
        message="Supply dispatched successfully.",
    )


@router.get(
    "/placements/{placement_id}/supplies",
    response_model=ApiResponse[list[FosterSupplyDispatchResponse]],
    dependencies=[Depends(require_permission("foster:read"))],
)
async def list_supply_dispatches(
    placement_id: uuid.UUID,
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[list[FosterSupplyDispatchResponse]]:
    dispatches = await service.list_supply_dispatches(placement_id)
    return ApiResponse(
        data=[FosterSupplyDispatchResponse.model_validate(d) for d in dispatches],
    )


@router.post(
    "/placements/{placement_id}/convert-to-adopt",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("foster:approve"))],
)
async def convert_to_adopt(
    placement_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[dict]:
    ip = request.client.host if request.client else None
    app = await service.convert_to_adoption(
        placement_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data={"adoption_id": str(app.id)},
        message="Foster placement converted to adoption successfully.",
    )
