"""API router for the Adoption Management module.

Routers only validate and call services (RULE-004).
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.exceptions import ForbiddenError, parse_enum
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.adoption.models import (
    AdoptionFollowUp,
    AdoptionStatus,
    FollowUpStatus,
)
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import (
    AdoptionApplicationCreate,
    AdoptionApplicationResponse,
    AdoptionApplicationUpdate,
    AdoptionFeeUpdate,
    AdoptionFollowUpCreate,
    AdoptionFollowUpResponse,
    AdoptionScoreCreate,
    AdoptionScoreResponse,
    AdoptionStatusUpdate,
    FollowUpProofCreate,
)
from pawguard.modules.adoption.service import AdoptionService
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import has_permission, require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.storage.schemas import DownloadUrlResponse
from pawguard.redis.client import RedisClient, get_redis
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService

router = APIRouter(prefix="/adoptions", tags=["adoptions"])



def get_adoption_service(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    audit: AuditService = Depends(get_audit_service),
) -> AdoptionService:
    repo = AdoptionRepository(db)
    dog_repo = DogRepository(db)
    storage_svc = StorageService()
    return AdoptionService(
        repo, dog_repo, redis_client=redis, audit_service=audit, storage_service=storage_svc
    )



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

    if app.adopter_id != current_user.user.id and not has_permission(
        current_user.user, "adoption:read"
    ):
        raise ForbiddenError("You do not have permission to view this application.")

    return ApiResponse(data=AdoptionApplicationResponse.model_validate(app))


@router.get(
    "/{app_id}/agreement",
    response_model=ApiResponse[DownloadUrlResponse],
)
async def get_adoption_agreement(
    app_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[DownloadUrlResponse]:
    app = await service.get_application(app_id)
    if app.adopter_id != current_user.user.id and not has_permission(
        current_user.user, "adoption:read"
    ):
        raise ForbiddenError("You do not have permission to view this agreement.")
    if not app.adoption_agreement_url:
        from pawguard.core.exceptions import NotFoundError
        raise NotFoundError("Agreement not yet generated for this application.")
    storage = StorageService()
    download_url = storage.generate_presigned_download_url(object_key=app.adoption_agreement_url)
    return ApiResponse(
        data=DownloadUrlResponse(
            download_url=download_url,
            object_key=app.adoption_agreement_url,
            file_id=app.id,
        ),
    )


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


@router.post(
    "/{app_id}/scores",
    response_model=ApiResponse[AdoptionScoreResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("adoption:process"))],
)
async def add_score(
    app_id: uuid.UUID,
    payload: AdoptionScoreCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionScoreResponse]:
    score = await service.add_score(
        app_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=AdoptionScoreResponse.model_validate(score),
        message="Adoption score added successfully.",
    )


@router.get(
    "/{app_id}/scores",
    response_model=ApiResponse[list[AdoptionScoreResponse]],
)
async def get_scores(
    app_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[list[AdoptionScoreResponse]]:
    app = await service.get_application(app_id)

    if app.adopter_id != current_user.user.id and not has_permission(
        current_user.user, "adoption:read"
    ):
        raise ForbiddenError("You do not have permission to view these scores.")
    scores = await service.get_scores(app_id)
    return ApiResponse(
        data=[AdoptionScoreResponse.model_validate(s) for s in scores],
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
    "/{app_id}/follow-ups",
    response_model=ApiResponse[AdoptionFollowUpResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("adoption:process"))],
)
async def create_follow_up(
    app_id: uuid.UUID,
    payload: AdoptionFollowUpCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionFollowUpResponse]:
    app = await service.get_application(app_id)
    follow_up = await service._repo.create_follow_up(
        AdoptionFollowUp(
            adoption_application_id=app_id,
            due_day=payload.due_day,
            due_at=app.completed_at
            + timedelta(days=payload.due_day)
            if app.completed_at
            else datetime.now(UTC) + timedelta(days=payload.due_day),
            status=FollowUpStatus.PENDING,
        )
    )
    return ApiResponse(
        data=AdoptionFollowUpResponse.model_validate(follow_up),
        message="Follow-up milestone created.",
    )


@router.get(
    "/{app_id}/follow-ups",
    response_model=ApiResponse[list[AdoptionFollowUpResponse]],
)
async def get_follow_ups(
    app_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[list[AdoptionFollowUpResponse]]:
    app = await service.get_application(app_id)
    if app.adopter_id != current_user.user.id and not has_permission(
        current_user.user, "adoption:read"
    ):
        raise ForbiddenError(
            "You do not have permission to view follow-ups for this application."
        )
    follow_ups = await service.get_follow_ups(app_id)
    return ApiResponse(
        data=[AdoptionFollowUpResponse.model_validate(fu) for fu in follow_ups],
    )


@router.post(
    "/{app_id}/follow-ups/{follow_up_id}/proof",
    response_model=ApiResponse[AdoptionFollowUpResponse],
)
async def submit_follow_up_proof(
    app_id: uuid.UUID,
    follow_up_id: uuid.UUID,
    payload: FollowUpProofCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionFollowUpResponse]:
    app = await service.get_application(app_id)
    if (
        app.adopter_id != current_user.user.id
        and not has_permission(current_user.user, "adoption:process")
    ):
        raise ForbiddenError(
            "You do not have permission to submit proof for this follow-up."
        )
    follow_up = await service.record_followup_proof(
        follow_up_id,
        media_keys=payload.media_keys,
        notes=payload.notes,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=AdoptionFollowUpResponse.model_validate(follow_up),
        message="Follow-up proof submitted successfully.",
    )


@router.put(
    "/{app_id}/fee",
    response_model=ApiResponse[AdoptionApplicationResponse],
    dependencies=[Depends(require_permission("adoption:process"))],
)
async def update_adoption_fee(
    app_id: uuid.UUID,
    payload: AdoptionFeeUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionApplicationResponse]:
    app = await service.update_adoption_fee(
        app_id,
        payload.fee_amount,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=AdoptionApplicationResponse.model_validate(app),
        message="Adoption fee updated successfully.",
    )


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
        parse_enum(AdoptionStatus, payload.status),
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
