"""API router for the Adoption Management module.

Routers only validate and call services (RULE-004).
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.exceptions import ForbiddenError
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.adoption.models import AdoptionStatus
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import (
    AdoptionApplicationCreate,
    AdoptionApplicationResponse,
    AdoptionApplicationUpdate,
    AdoptionStatusUpdate,
)
from pawguard.modules.adoption.service import AdoptionService
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/adoptions", tags=["adoptions"])


def get_adoption_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> AdoptionService:
    repo = AdoptionRepository(db)
    dog_repo = DogRepository(db)
    return AdoptionService(repo, dog_repo, audit_service=audit)


@router.post(
    "",
    response_model=ApiResponse[AdoptionApplicationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def apply_for_adoption(
    payload: AdoptionApplicationCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionApplicationResponse]:
    app = await service.apply_for_adoption(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=AdoptionApplicationResponse.model_validate(app),
        message="Adoption application submitted successfully.",
    )


@router.get(
    "",
    response_model=PaginatedResponse[AdoptionApplicationResponse],
    dependencies=[Depends(require_permission("adoption:read"))],
)
async def list_applications(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by notes, residential status"),
    status: AdoptionStatus | None = Query(None, description="Filter by status"),
    dog_id: uuid.UUID | None = Query(None, description="Filter by dog ID"),
    adopter_id: uuid.UUID | None = Query(None, description="Filter by adopter ID"),
    service: AdoptionService = Depends(get_adoption_service),
) -> PaginatedResponse[AdoptionApplicationResponse]:
    return await service.list_applications_paginated(
        page=page,
        sort=sort,
        search_term=search,
        status=status,
        dog_id=dog_id,
        adopter_id=adopter_id,
    )


@router.get(
    "/{app_id}",
    response_model=ApiResponse[AdoptionApplicationResponse],
)
async def get_application(
    app_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionApplicationResponse]:
    app = await service.get_application(app_id)

    user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
    if app.adopter_id != current_user.user.id and "adoption:read" not in user_permissions:
        raise ForbiddenError("You do not have permission to view this application.")

    return ApiResponse(data=AdoptionApplicationResponse.model_validate(app))


@router.put(
    "/{app_id}",
    response_model=ApiResponse[AdoptionApplicationResponse],
    dependencies=[Depends(require_permission("adoption:process"))],
)
async def update_application(
    app_id: uuid.UUID,
    payload: AdoptionApplicationUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionApplicationResponse]:
    app = await service.update_application(
        app_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=AdoptionApplicationResponse.model_validate(app),
        message="Adoption application updated successfully.",
    )


@router.patch(
    "/{app_id}/status",
    response_model=ApiResponse[AdoptionApplicationResponse],
    dependencies=[Depends(require_permission("adoption:process"))],
)
async def update_application_status(
    app_id: uuid.UUID,
    payload: AdoptionStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionApplicationResponse]:
    app = await service.update_application_status(
        app_id,
        payload.status,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=AdoptionApplicationResponse.model_validate(app),
        message="Adoption application status updated successfully.",
    )


@router.delete(
    "/{app_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("adoption:process"))],
)
async def soft_delete_application(
    app_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[None]:
    await service.soft_delete_application(
        app_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(message="Adoption application deleted successfully.")


@router.post(
    "/bulk/status-update",
    response_model=ApiResponse[BulkStatusUpdateResponse],
    dependencies=[Depends(require_permission("adoption:process"))],
)
async def bulk_update_application_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[BulkStatusUpdateResponse]:
    updated = await service.bulk_update_status(
        payload.ids,
        AdoptionStatus(payload.status),
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkStatusUpdateResponse(
            message=f"{updated} adoption application(s) status updated.",
            updated_count=updated,
        ),
    )


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("adoption:process"))],
)
async def bulk_delete_applications(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[BulkDeleteResponse]:
    deleted = await service.bulk_soft_delete(
        payload.ids,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} adoption application(s) deleted.",
            deleted_count=deleted,
        ),
    )
