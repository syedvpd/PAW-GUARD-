"""API router for the Emergency Rescue module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import get_current_user, CurrentUser
from pawguard.modules.auth.models import User
from pawguard.modules.auth.rbac import require_permission
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

router = APIRouter(prefix="/rescue", tags=["rescue"])


def get_rescue_service(db: AsyncSession = Depends(get_db)) -> RescueService:
    repo = RescueRepository(db)
    return RescueService(repo)


@router.post(
    "/report",
    response_model=ApiResponse[RescueRequestResponse],
    status_code=status.HTTP_201_CREATED,
)
async def report_incident(
    payload: RescueRequestCreate,
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    request = await service.report_incident(
        reporter_name=payload.reporter_name,
        reporter_phone=payload.reporter_phone,
        reporter_email=payload.reporter_email,
        is_anonymous=payload.is_anonymous,
        location_address=payload.location_address,
        location_landmark=payload.location_landmark,
        latitude=payload.latitude,
        longitude=payload.longitude,
        animal_count=payload.animal_count,
        physical_condition=payload.physical_condition,
        behavioral_indicators=payload.behavioral_indicators,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request),
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
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    approve = payload.status == RescueStatus.VERIFIED
    request = await service.verify_request(
        request_id, approve=approve, rationale=payload.rejection_rationale
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request),
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
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    request = await service.dispatch_team(
        request_id,
        assigned_driver_id=payload.assigned_driver_id,
        vehicle_id=payload.vehicle_id,
        equipment_details=payload.equipment_details,
        notes=payload.notes,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request),
        message="Rescue vehicle and team dispatched successfully.",
    )


@router.post(
    "/{request_id}/located",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:execute"))],
)
async def mark_located(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    request = await service.update_dispatch_status(
        request_id, status=RescueStatus.LOCATED, agent_id=current_user.id
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request),
        message="Rescue location reached.",
    )


@router.post(
    "/{request_id}/secured",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:execute"))],
)
async def mark_rescued(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    request = await service.update_dispatch_status(
        request_id, status=RescueStatus.RESCUED, agent_id=current_user.id
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request),
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
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    request = await service.update_dispatch_status(
        request_id,
        status=RescueStatus.ADMITTED,
        agent_id=current_user.id,
        notes=payload.notes,
        photos=payload.photos,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request),
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
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    request = await service.update_dispatch_status(
        request_id,
        status=RescueStatus.REJECTED,
        agent_id=current_user.id,
        failure_reason=failure_reason,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request),
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
    response_model=ApiResponse[list[RescueRequestResponse]],
    dependencies=[Depends(require_permission("rescue:read"))],
)
async def list_requests(
    status: RescueStatus | None = None,
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[list[RescueRequestResponse]]:
    requests = await service.list_requests(status)
    return ApiResponse(data=[RescueRequestResponse.model_validate(r) for r in requests])
