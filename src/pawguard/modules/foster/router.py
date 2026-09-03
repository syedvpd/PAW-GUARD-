"""API router for the Foster Management module.

Routers only validate and call services (RULE-004).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
)
from pawguard.core.exceptions import ForbiddenError
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.rate_limiter import rate_limit
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import has_permission, require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.foster.models import FosterStatus
from pawguard.modules.foster.repository import FosterRepository
from pawguard.modules.foster.schemas import (
    FosterBackgroundCheckInitiate,
    FosterBackgroundCheckOutcome,
    FosterBehaviorLogCreate,
    FosterHomeInspectionLog,
    FosterHomeInspectionOutcome,
    FosterHomeInspectionSchedule,
    FosterMediaLogCreate,
    FosterMedicationLogCreate,
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
    FosterVetCheckRequest,
    FosterVetCheckResponse,
    FosterWeightLogCreate,
)
from pawguard.modules.foster.service import FosterService
from pawguard.services.audit_service import AuditService

router = APIRouter(tags=["fosters"])


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
    _: Annotated[None, Depends(rate_limit("foster_apply", 5, 3600))] = None,
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


@router.get(
    "/me",
    response_model=ApiResponse[FosterProfileResponse],
)
async def get_my_foster_profile(
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    profile = await service.get_my_profile(current_user.user.id)
    return ApiResponse(data=FosterProfileResponse.model_validate(profile))


@router.get(
    "/me/placements",
    response_model=ApiResponse[list[FosterPlacementResponse]],
)
async def get_my_foster_placements(
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[list[FosterPlacementResponse]]:
    placements = await service.get_my_placements(current_user.user.id)
    return ApiResponse(data=[FosterPlacementResponse.model_validate(p) for p in placements])


@router.put(
    "/{profile_id}",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:update", "foster:approve"))],
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


@router.post(
    "/{profile_id}/approve",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
async def approve_profile(
    profile_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    ip = request.client.host if request.client else None
    profile = await service.update_profile(
        profile_id,
        FosterProfileUpdate(status=FosterStatus.APPROVED),
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProfileResponse.model_validate(profile),
        message="Foster profile approved successfully.",
    )


@router.delete(
    "/{profile_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("foster:update"))],
)
@router.delete(
    "/admin/fosters/{profile_id}",
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


@router.get(
    "/{profile_id}/placements",
    response_model=ApiResponse[list[FosterPlacementResponse]],
    dependencies=[Depends(require_permission("foster:read"))],
)
async def list_foster_placements(
    profile_id: uuid.UUID,
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[list[FosterPlacementResponse]]:
    """Coordinator/admin view of the dogs assigned to a specific foster."""
    placements = await service.get_placements_for_profile(profile_id)
    return ApiResponse(data=[FosterPlacementResponse.model_validate(p) for p in placements])


@router.post(
    "/placements/{placement_id}/return",
    response_model=ApiResponse[FosterPlacementResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.post(
    "/placements/{placement_id}/return-to-shelter",
    response_model=ApiResponse[FosterPlacementResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.put(
    "/placements/{placement_id}/return",
    response_model=ApiResponse[FosterPlacementResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.put(
    "/placements/{placement_id}/return-to-shelter",
    response_model=ApiResponse[FosterPlacementResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.post(
    "/{placement_id}/return",
    response_model=ApiResponse[FosterPlacementResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.post(
    "/{placement_id}/return-to-shelter",
    response_model=ApiResponse[FosterPlacementResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
async def return_dog(
    placement_id: uuid.UUID,
    request: Request,
    payload: FosterReturnRequest = FosterReturnRequest(),
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


@router.post(
    "/placements/{placement_id}/vet-check",
    response_model=ApiResponse[FosterVetCheckResponse],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/placements/{placement_id}/request-vet-check",
    response_model=ApiResponse[FosterVetCheckResponse],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{placement_id}/vet-check",
    response_model=ApiResponse[FosterVetCheckResponse],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{placement_id}/request-vet-check",
    response_model=ApiResponse[FosterVetCheckResponse],
    status_code=status.HTTP_201_CREATED,
)
async def request_vet_check(
    placement_id: uuid.UUID,
    request: Request,
    payload: FosterVetCheckRequest = FosterVetCheckRequest(),
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterVetCheckResponse]:
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    is_authorized = (
        is_owner
        or has_permission(current_user.user, "foster:approve")
        or has_permission(current_user.user, "foster:update")
        or has_permission(current_user.user, "foster:read")
        or has_permission(current_user.user, "medical:create")
    )
    if not is_authorized:
        raise ForbiddenError(
            "You do not have permission to request a vet check for this placement."
        )
    ip = request.client.host if request.client else None
    result = await service.request_vet_check(
        placement_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=result,
        message="Veterinary check requested successfully.",
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
)
@router.post(
    "/{placement_id}/progress",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
)
async def log_progress(
    placement_id: uuid.UUID,
    payload: FosterProgressLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProgressLogResponse]:
    # The foster family that owns the placement logs daily updates; foster
    # coordinators (foster:approve) may also log on their behalf.
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    if (
        not is_owner
        and not has_permission(current_user.user, "foster:approve")
        and not has_permission(current_user.user, "foster:update")
    ):
        raise ForbiddenError("You do not have permission to log progress for this placement.")
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


@router.post(
    "/placements/{placement_id}/progress/weight",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{placement_id}/progress/weight",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
)
async def log_weight(
    placement_id: uuid.UUID,
    payload: FosterWeightLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProgressLogResponse]:
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    if (
        not is_owner
        and not has_permission(current_user.user, "foster:approve")
        and not has_permission(current_user.user, "foster:update")
    ):
        raise ForbiddenError("You do not have permission to log weight for this placement.")
    ip = request.client.host if request.client else None
    log = await service.log_weight(
        placement_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProgressLogResponse.model_validate(log),
        message="Weight progress logged and synced to dog profile.",
    )


@router.post(
    "/placements/{placement_id}/progress/behavior",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{placement_id}/progress/behavior",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
)
async def log_behavior(
    placement_id: uuid.UUID,
    payload: FosterBehaviorLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProgressLogResponse]:
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    if (
        not is_owner
        and not has_permission(current_user.user, "foster:approve")
        and not has_permission(current_user.user, "foster:update")
    ):
        raise ForbiddenError("You do not have permission to log behavior for this placement.")
    ip = request.client.host if request.client else None
    log = await service.log_behavior(
        placement_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProgressLogResponse.model_validate(log),
        message="Behavioral observations logged successfully.",
    )


@router.post(
    "/placements/{placement_id}/progress/medication",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{placement_id}/progress/medication",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
)
async def log_medication(
    placement_id: uuid.UUID,
    payload: FosterMedicationLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProgressLogResponse]:
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    if (
        not is_owner
        and not has_permission(current_user.user, "foster:approve")
        and not has_permission(current_user.user, "foster:update")
    ):
        raise ForbiddenError("You do not have permission to log medication for this placement.")
    ip = request.client.host if request.client else None
    log = await service.log_medication(
        placement_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProgressLogResponse.model_validate(log),
        message="Medication verification check-in logged successfully.",
    )


@router.post(
    "/placements/{placement_id}/progress/media",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{placement_id}/progress/media",
    response_model=ApiResponse[FosterProgressLogResponse],
    status_code=status.HTTP_201_CREATED,
)
async def log_media(
    placement_id: uuid.UUID,
    payload: FosterMediaLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProgressLogResponse]:
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    if (
        not is_owner
        and not has_permission(current_user.user, "foster:approve")
        and not has_permission(current_user.user, "foster:update")
    ):
        raise ForbiddenError("You do not have permission to log media for this placement.")
    ip = request.client.host if request.client else None
    log = await service.log_media(
        placement_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProgressLogResponse.model_validate(log),
        message="Media uploads logged successfully.",
    )


@router.get(
    "/placements/{placement_id}/progress",
    response_model=ApiResponse[list[FosterProgressLogResponse]],
)
@router.get(
    "/{placement_id}/progress",
    response_model=ApiResponse[list[FosterProgressLogResponse]],
)
async def get_progress_logs(
    placement_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[list[FosterProgressLogResponse]]:
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    if (
        not is_owner
        and not has_permission(current_user.user, "foster:update")
        and not has_permission(current_user.user, "foster:read")
    ):
        raise ForbiddenError("You do not have permission to view these progress logs.")
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
)
async def list_supply_dispatches(
    placement_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[list[FosterSupplyDispatchResponse]]:
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    if (
        not is_owner
        and not has_permission(current_user.user, "foster:update")
        and not has_permission(current_user.user, "foster:read")
    ):
        raise ForbiddenError("You do not have permission to view these supply dispatches.")
    dispatches = await service.list_supply_dispatches(placement_id)
    return ApiResponse(
        data=[FosterSupplyDispatchResponse.model_validate(d) for d in dispatches],
    )


@router.post(
    "/placements/{placement_id}/supplies/request",
    response_model=ApiResponse[FosterSupplyDispatchResponse],
    status_code=status.HTTP_201_CREATED,
)
async def request_supplies(
    placement_id: uuid.UUID,
    payload: FosterSupplyDispatchCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterSupplyDispatchResponse]:
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    if (
        not is_owner
        and not has_permission(current_user.user, "foster:approve")
        and not has_permission(current_user.user, "foster:update")
    ):
        raise ForbiddenError("You do not have permission to request supplies for this placement.")
    ip = request.client.host if request.client else None
    dispatch = await service.request_supplies(
        placement_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterSupplyDispatchResponse.model_validate(dispatch),
        message="Supply request submitted successfully.",
    )


@router.post(
    "/placements/{placement_id}/convert-to-adopt",
    response_model=ApiResponse[dict[str, Any]],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/placements/{placement_id}/convert",
    response_model=ApiResponse[dict[str, Any]],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{placement_id}/convert-to-adopt",
    response_model=ApiResponse[dict[str, Any]],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{placement_id}/convert",
    response_model=ApiResponse[dict[str, Any]],
    status_code=status.HTTP_201_CREATED,
)
async def convert_to_adopt(
    placement_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[dict[str, Any]]:
    placement = await service.get_placement(placement_id)
    is_owner = (
        placement.foster.user_id == current_user.user.id
        if (placement.foster and hasattr(placement.foster, "user_id"))
        else False
    )
    is_authorized = (
        is_owner
        or has_permission(current_user.user, "foster:approve")
        or has_permission(current_user.user, "foster:update")
        or has_permission(current_user.user, "adoption:create")
    )
    if not is_authorized:
        raise ForbiddenError("You do not have permission to convert this placement to adoption.")
    ip = request.client.host if request.client else None
    app = await service.convert_to_adoption(
        placement_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data={
            "adoption_id": str(app.id),
            "status": app.status.value,
            "dog_id": str(app.dog_id),
            "adoption_agreement_url": app.adoption_agreement_url,
        },
        message="Foster placement converted to adoption successfully.",
    )


@router.post(
    "/{profile_id}/background-check/initiate",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
async def initiate_background_check(
    profile_id: uuid.UUID,
    request: Request,
    payload: FosterBackgroundCheckInitiate = FosterBackgroundCheckInitiate(),
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    ip = request.client.host if request.client else None
    profile = await service.initiate_background_check(
        profile_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProfileResponse.model_validate(profile),
        message="Background check initiated successfully.",
    )


@router.post(
    "/{profile_id}/background-check/outcome",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.post(
    "/{profile_id}/background-check",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.put(
    "/{profile_id}/background-check",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
async def record_background_check_outcome(
    profile_id: uuid.UUID,
    payload: FosterBackgroundCheckOutcome,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    ip = request.client.host if request.client else None
    profile = await service.record_background_check_outcome(
        profile_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProfileResponse.model_validate(profile),
        message="Background check outcome recorded successfully.",
    )


@router.post(
    "/{profile_id}/home-inspection/schedule",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
async def schedule_home_inspection(
    profile_id: uuid.UUID,
    payload: FosterHomeInspectionSchedule,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    ip = request.client.host if request.client else None
    profile = await service.schedule_home_inspection(
        profile_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProfileResponse.model_validate(profile),
        message="Home inspection scheduled successfully.",
    )


@router.post(
    "/{profile_id}/home-inspection/log",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.post(
    "/{profile_id}/home-inspection/audit",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
async def log_home_inspection(
    profile_id: uuid.UUID,
    payload: FosterHomeInspectionLog,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    ip = request.client.host if request.client else None
    profile = await service.log_home_inspection_audit(
        profile_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProfileResponse.model_validate(profile),
        message="Home inspection audit details recorded successfully.",
    )


@router.post(
    "/{profile_id}/home-inspection/outcome",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.post(
    "/{profile_id}/home-inspection",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
@router.put(
    "/{profile_id}/home-inspection",
    response_model=ApiResponse[FosterProfileResponse],
    dependencies=[Depends(require_permission("foster:approve", "foster:update"))],
)
async def record_home_inspection_outcome(
    profile_id: uuid.UUID,
    payload: FosterHomeInspectionOutcome,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FosterService = Depends(get_foster_service),
) -> ApiResponse[FosterProfileResponse]:
    ip = request.client.host if request.client else None
    profile = await service.record_home_inspection_outcome(
        profile_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FosterProfileResponse.model_validate(profile),
        message="Home inspection outcome recorded successfully.",
    )
