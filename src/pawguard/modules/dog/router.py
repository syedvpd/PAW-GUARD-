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
from pawguard.core.exceptions import NotFoundError, parse_enum
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.rate_limiter import resolve_client_ip
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
from pawguard.modules.dog.models import (
    DogBreedClassification,
    DogGender,
    DogStatus,
    DogTemperament,
)
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.schemas import (
    DogActivityLogResponse,
    DogProfileCreate,
    DogProfileResponse,
    DogProfileUpdate,
    DogStatusUpdate,
    DogWeightLogCreate,
    DogWeightLogResponse,
)
from pawguard.modules.dog.service import DogService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/dogs", tags=["dogs"])


def get_dog_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> DogService:
    return DogService(DogRepository(db), audit_service=audit)


def _public_dog_view(dog: DogProfileResponse) -> DogProfileResponse:
    """Public adoption-directory view: strips internal identifiers (rescue
    case link, microchip, facility/section/kennel/foster-home UUIDs) that are
    meaningless - and potentially sensitive - on the anonymous public catalog."""
    return dog.model_copy(
        update={
            "microchip_id": None,
            "rescue_case_id": None,
            "shelter_facility_id": None,
            "section_id": None,
            "kennel_id": None,
            "foster_home_id": None,
        }
    )


def _public_view_enabled(current_user: CurrentUser | None) -> bool:
    """Anonymous visitors - and signed-in users without the public:read
    permission - only see the adoptable, identifier-stripped catalog. Users
    who hold public:read (assigned to every seeded role) keep the full view,
    preserving the previous permission gate exactly."""
    if current_user is None:
        return True
    perms = {p.code for r in current_user.user.roles for p in r.permissions}
    return "public:read" not in perms


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
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog profile registered successfully.",
    )


@router.get(
    "",
    response_model=PaginatedResponse[DogProfileResponse],
)
async def list_dogs(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by name, breed, registration number"),
    status: DogStatus | None = Query(None, description="Filter by status"),
    is_adoptable: bool | None = Query(None, description="Filter by adoptable status"),
    breed: str | None = Query(None, description="Filter by breed"),
    breed_classification: DogBreedClassification | None = Query(
        None, description="Filter by Pure/Mix/Unknown classification"
    ),
    gender: DogGender | None = Query(None, description="Filter by sex"),
    temperament: DogTemperament | None = Query(None, description="Filter by temperament"),
    min_age_months: int | None = Query(None, ge=0, description="Minimum age in months"),
    max_age_months: int | None = Query(None, ge=0, description="Maximum age in months"),
    min_weight: float | None = Query(None, ge=0.0, description="Minimum weight in kg"),
    max_weight: float | None = Query(None, ge=0.0, description="Maximum weight in kg"),
    location: str | None = Query(
        None, description=(
            "Free-text match on the shelter facility name/address; only dogs "
            "assigned to a facility are returned when this filter is active"
        )
    ),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: DogService = Depends(get_dog_service),
) -> PaginatedResponse[DogProfileResponse]:
    public_view = _public_view_enabled(current_user)
    # The public adoption directory (PRR 3.1.4) only shows adoptable dogs.
    if public_view:
        is_adoptable = True
    result = await service.list_dogs_paginated(
        page=page,
        sort=sort,
        search_term=search,
        status=status,
        is_adoptable=is_adoptable,
        breed=breed,
        breed_classification=breed_classification,
        gender=gender,
        temperament=temperament,
        min_age_months=min_age_months,
        max_age_months=max_age_months,
        min_weight=min_weight,
        max_weight=max_weight,
        location=location,
    )
    data = [DogProfileResponse.model_validate(d) for d in result.data]
    if public_view:
        data = [_public_dog_view(d) for d in data]
    return PaginatedResponse(data=data, meta=result.meta)


@router.get(
    "/{dog_id}",
    response_model=ApiResponse[DogProfileResponse],
)
async def get_dog(
    dog_id: uuid.UUID,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.get_dog(dog_id)
    public_view = _public_view_enabled(current_user)
    # Public visitors must not see non-adoptable (internal) dogs by ID.
    if public_view and not dog.is_adoptable:
        raise NotFoundError("Dog profile not found.")
    data = DogProfileResponse.model_validate(dog)
    if public_view:
        data = _public_dog_view(data)
    return ApiResponse(data=data)


@router.get(
    "/{dog_id}/timeline",
    response_model=ApiResponse[list[DogActivityLogResponse]],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def get_dog_timeline(
    dog_id: uuid.UUID,
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[list[DogActivityLogResponse]]:
    """Lifecycle activity stream for a dog's master profile (PRR 3.4)."""
    logs = await service.get_dog_timeline(dog_id)
    return ApiResponse(
        data=[DogActivityLogResponse.model_validate(log) for log in logs],
        message=f"{len(logs)} activity event(s).",
    )


@router.post(
    "/{dog_id}/weight",
    response_model=ApiResponse[DogWeightLogResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def record_dog_weight(
    dog_id: uuid.UUID,
    payload: DogWeightLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogWeightLogResponse]:
    """Append a weight measurement to a dog's history (PRR 3.4)."""
    log = await service.record_weight(
        dog_id,
        payload,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=DogWeightLogResponse.model_validate(log),
        message="Weight recorded successfully.",
    )


@router.get(
    "/{dog_id}/weights",
    response_model=ApiResponse[list[DogWeightLogResponse]],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def get_dog_weight_history(
    dog_id: uuid.UUID,
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[list[DogWeightLogResponse]]:
    """Chronological weight history for a dog (PRR 3.4)."""
    logs = await service.get_weight_history(dog_id)
    return ApiResponse(
        data=[DogWeightLogResponse.model_validate(log) for log in logs],
        message=f"{len(logs)} weight record(s).",
    )


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
        ip_address=resolve_client_ip(request),
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
        ip_address=resolve_client_ip(request),
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
        ip_address=resolve_client_ip(request),
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
        ip_address=resolve_client_ip(request),
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
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} dog(s) deleted.",
            deleted_count=deleted,
        ),
    )
