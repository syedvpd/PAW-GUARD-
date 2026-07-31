"""API router for the Emergency Rescue module.

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
from pawguard.core.exceptions import parse_enum
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.rescue.models import RescueStatus
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.schemas import (
    RescueDispatchCreate,
    RescueReportCreate,
    RescueRequestCreate,
    RescueRequestResponse,
    RescueRequestUpdate,
)
from pawguard.modules.rescue.service import RescueService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/rescue", tags=["rescue"])


def get_rescue_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> RescueService:
    repo = RescueRepository(db)
    dog_repo = DogRepository(db)
    return RescueService(repo, audit_service=audit, dog_repo=dog_repo)


@router.post(
    "/report",
    response_model=ApiResponse[RescueRequestResponse],
    status_code=status.HTTP_201_CREATED,
)
async def report_incident(
    payload: RescueRequestCreate,
    request: Request,
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    request_obj = await service.report_incident(
        reporter_name=payload.reporter_name,
        reporter_phone=payload.reporter_phone,
        reporter_alternate_phone=payload.reporter_alternate_phone,
        reporter_email=payload.reporter_email,
        is_anonymous=payload.is_anonymous,
        location_address=payload.location_address,
        location_landmark=payload.location_landmark,
        latitude=payload.latitude,
        longitude=payload.longitude,
        animal_count=payload.animal_count,
        physical_condition=payload.physical_condition,
        behavioral_indicators=payload.behavioral_indicators,
        actor_id=None,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request_obj),
        message="Emergency incident reported successfully.",
    )


@router.post(
    "/{request_id}/verify",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:verify"))],
)
async def verify_request(
    request_id: uuid.UUID,
    payload: RescueRequestUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    approve = payload.status == RescueStatus.VERIFIED
    rescue = await service.verify_request(
        request_id,
        approve=approve,
        rationale=payload.rejection_rationale,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(rescue),
        message="Rescue incident verification updated.",
    )


@router.post(
    "/{request_id}/dispatch",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:dispatch"))],
)
async def dispatch_team(
    request_id: uuid.UUID,
    payload: RescueDispatchCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    rescue = await service.dispatch_team(
        request_id,
        assigned_driver_id=payload.assigned_driver_id,
        vehicle_id=payload.vehicle_id,
        equipment_details=payload.equipment_details,
        notes=payload.notes,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(rescue),
        message="Rescue vehicle and team dispatched successfully.",
    )


@router.post(
    "/{request_id}/located",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:execute"))],
)
async def mark_located(
    request_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    rescue = await service.update_dispatch_status(
        request_id,
        status=RescueStatus.LOCATED,
        agent_id=current_user.id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(rescue),
        message="Rescue location reached.",
    )


@router.post(
    "/{request_id}/secured",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:execute"))],
)
async def mark_rescued(
    request_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    rescue = await service.update_dispatch_status(
        request_id,
        status=RescueStatus.RESCUED,
        agent_id=current_user.id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(rescue),
        message="Animal secured and placed in transit.",
    )


@router.post(
    "/{request_id}/admitted",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:execute"))],
)
async def mark_admitted(
    request_id: uuid.UUID,
    payload: RescueReportCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    rescue = await service.update_dispatch_status(
        request_id,
        status=RescueStatus.ADMITTED,
        agent_id=current_user.id,
        notes=payload.notes,
        photos=payload.photos,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(rescue),
        message="Animal admitted and registered at shelter facility.",
    )


@router.post(
    "/{request_id}/fail",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:execute"))],
)
async def fail_rescue(
    request_id: uuid.UUID,
    failure_reason: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    rescue = await service.update_dispatch_status(
        request_id,
        status=RescueStatus.REJECTED,
        agent_id=current_user.id,
        failure_reason=failure_reason,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(rescue),
        message="Rescue operation marked failed.",
    )


@router.get(
    "/{request_id}",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:read"))],
)
async def get_request(
    request_id: uuid.UUID,
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    request = await service.get_request(request_id)
    return ApiResponse(data=RescueRequestResponse.model_validate(request))


@router.get(
    "",
    response_model=PaginatedResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:read"))],
)
async def list_requests(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(
        None, description="Search by ticket number, reporter name, phone, or location"
    ),
    status: RescueStatus | None = Query(None, description="Filter by status"),
    service: RescueService = Depends(get_rescue_service),
) -> PaginatedResponse[RescueRequestResponse]:
    return await service.list_requests_paginated(
        page=page, sort=sort, search_term=search, status=status
    )


@router.delete(
    "/{request_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("rescue:execute"))],
)
async def soft_delete_request(
    request_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[None]:
    await service.soft_delete_request(
        request_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(message="Rescue request deleted successfully.")


@router.post(
    "/bulk/status-update",
    response_model=ApiResponse[BulkStatusUpdateResponse],
    dependencies=[Depends(require_permission("rescue:execute"))],
)
async def bulk_update_rescue_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[BulkStatusUpdateResponse]:
    updated = await service.bulk_update_status(
        payload.ids,
        parse_enum(RescueStatus, payload.status),
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkStatusUpdateResponse(
            message=f"{updated} rescue request(s) status updated.",
            updated_count=updated,
        ),
    )


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("rescue:execute"))],
)
async def bulk_delete_rescue_requests(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[BulkDeleteResponse]:
    deleted = await service.bulk_soft_delete(
        payload.ids,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} rescue request(s) deleted.",
            deleted_count=deleted,
        ),
    )
