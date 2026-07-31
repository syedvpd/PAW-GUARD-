"""API router for the Dog Management module. Routers only validate and call services (RULE-004)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
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
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.schemas import (
    DogProfileCreate,
    DogProfileResponse,
    DogProfileUpdate,
    DogStatusUpdate,
)
from pawguard.modules.dog.service import DogService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/dogs", tags=["dogs"])


def get_dog_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> DogService:
    return DogService(DogRepository(db), audit_service=audit)


@router.post(
    "",
    response_model=ApiResponse[DogProfileResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def register_dog(
    payload: DogProfileCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.register_dog(
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog profile registered successfully.",
    )


@router.get(
    "",
    response_model=PaginatedResponse[DogProfileResponse],
    dependencies=[Depends(require_permission("public:read"))],
)
async def list_dogs(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by name, breed, registration number"),
    status: DogStatus | None = Query(None, description="Filter by status"),
    is_adoptable: bool | None = Query(None, description="Filter by adoptable status"),
    breed: str | None = Query(None, description="Filter by breed"),
    gender: str | None = Query(None, description="Filter by gender"),
    temperament: str | None = Query(None, description="Filter by temperament"),
    service: DogService = Depends(get_dog_service),
) -> PaginatedResponse[DogProfileResponse]:
    return await service.list_dogs_paginated(
        page=page,
        sort=sort,
        search_term=search,
        status=status,
        is_adoptable=is_adoptable,
        breed=breed,
        gender=gender,
        temperament=temperament,
    )


@router.get(
    "/{dog_id}",
    response_model=ApiResponse[DogProfileResponse],
    dependencies=[Depends(require_permission("public:read"))],
)
async def get_dog(
    dog_id: uuid.UUID,
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.get_dog(dog_id)
    return ApiResponse(data=DogProfileResponse.model_validate(dog))


@router.put(
    "/{dog_id}",
    response_model=ApiResponse[DogProfileResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_dog(
    dog_id: uuid.UUID,
    payload: DogProfileUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.update_dog(
        dog_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog profile updated successfully.",
    )


@router.patch(
    "/{dog_id}/status",
    response_model=ApiResponse[DogProfileResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_dog_status(
    dog_id: uuid.UUID,
    payload: DogStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.update_dog_status(
        dog_id,
        payload.status,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog status updated successfully.",
    )


@router.delete(
    "/{dog_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def soft_delete_dog(
    dog_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[None]:
    await service.soft_delete_dog(
        dog_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(message="Dog profile deleted successfully.")


@router.post(
    "/bulk/status-update",
    response_model=ApiResponse[BulkStatusUpdateResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_update_dog_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[BulkStatusUpdateResponse]:
    updated = await service.bulk_update_status(
        payload.ids,
        parse_enum(DogStatus, payload.status),
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkStatusUpdateResponse(
            message=f"{updated} dog(s) status updated.",
            updated_count=updated,
        ),
    )


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_delete_dogs(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[BulkDeleteResponse]:
    deleted = await service.bulk_soft_delete(
        payload.ids,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} dog(s) deleted.",
            deleted_count=deleted,
        ),
    )
