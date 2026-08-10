"""API router for the Emergency Rescue module.

Routers only validate and call services (RULE-004).
"""

import uuid
from typing import Any

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
from pawguard.core.pii import mask_email, mask_full_name, mask_phone
from pawguard.core.rate_limiter import rate_limit
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
from pawguard.modules.rescue.models import RescueRequest, RescueSeverity, RescueStatus
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.schemas import (
    PublicRescueStatusResponse,
    RescueDispatchCreate,
    RescueDispatchResponse,
    RescueDispatchUpdate,
    RescueEscalateCreate,
    RescueMediaUploadUrlRequest,
    RescueMediaUploadUrlResponse,
    RescueReportCreate,
    RescueRequestCreate,
    RescueRequestResponse,
    RescueRequestUpdate,
)
from pawguard.modules.rescue.service import RescueService
from pawguard.redis.client import RedisClient, get_redis
from pawguard.services.audit_service import AuditService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/rescue", tags=["rescue"])

# Public, anonymous emergency-reporting surface (PRR). Kept separate from the
# authenticated `/rescue/report` endpoint (which requires `rescue:create`) so
# the community can report strays/emergencies without an account while staff
# workflow reports stay permission-gated.
public_rescue_router = APIRouter(prefix="/public/rescue", tags=["public-rescue"])


def get_rescue_service(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    audit: AuditService = Depends(get_audit_service),
    arq_pool: Any = Depends(get_arq_pool),
) -> RescueService:
    repo = RescueRepository(db)
    dog_repo = DogRepository(db)
    return RescueService(
        repo, audit_service=audit, dog_repo=dog_repo, redis_client=redis, arq_pool=arq_pool
    )



# Roles allowed to see unmasked reporter PII on rescue cases. Per PRR §6.1
# reporter identity/contact is masked in general system views and unmasked
# only for coordinators and administrators.
_UNMASKED_RESCUE_PII_PERMISSIONS = {"rescue:verify", "rescue:dispatch", "system:admin"}


def _mask_reporter_pii(
    item: RescueRequestResponse, current_user: CurrentUser | None
) -> RescueRequestResponse:
    """Return a copy of the response with reporter PII masked unless the
    caller holds coordinator/admin permissions."""
    if current_user is not None:
        user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
        if _UNMASKED_RESCUE_PII_PERMISSIONS & user_permissions:
            return item
    return item.model_copy(
        update={
            "reporter_name": mask_full_name(item.reporter_name),
            "reporter_phone": mask_phone(item.reporter_phone),
            "reporter_alternate_phone": mask_phone(item.reporter_alternate_phone),
            "reporter_email": mask_email(item.reporter_email),
        }
    )



def _masked_rescue_response(
    rescue: RescueRequest,
    current_user: CurrentUser,
    *,
    message: str,
) -> ApiResponse[RescueRequestResponse]:
    """Build the standard rescue response with reporter PII masked per the
    caller's role - used by EVERY handler that returns a rescue request so
    the §6.1 masking policy can't be bypassed by switching HTTP verbs."""
    data = _mask_reporter_pii(
        RescueRequestResponse.model_validate(rescue), current_user
    )
    return ApiResponse(data=data, message=message)


@router.post(
    "/report",
    response_model=ApiResponse[RescueRequestResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit("rescue_report", 5, 60)),
        Depends(require_permission("rescue:create")),
    ],
)
async def report_incident(
    payload: RescueRequestCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
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
        severity=payload.severity,
        is_urgent=payload.is_urgent,
        media_evidence=payload.media_evidence,
        environmental_factors=payload.environmental_factors,
        reporter_notes=payload.reporter_notes,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request_obj),
        message="Emergency incident reported successfully.",
    )


@public_rescue_router.post(
    "/report",
    response_model=ApiResponse[RescueRequestResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("public_rescue_report", 5, 60))],
)
async def public_report_incident(
    payload: RescueRequestCreate,
    request: Request,
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    """Anonymous public emergency reporting (PRR).

    No authentication required. Reporter identity is optional and the case is
    created with ``actor_id=None``. Rate-limited to 5 requests/minute to deter
    spam. Staff-side workflow reporting remains on ``POST /rescue/report``.
    """
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
        severity=payload.severity,
        is_urgent=payload.is_urgent,
        media_evidence=payload.media_evidence,
        environmental_factors=payload.environmental_factors,
        reporter_notes=payload.reporter_notes,
        actor_id=None,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueRequestResponse.model_validate(request_obj),
        message="Emergency incident reported successfully.",
    )


@router.post(
    "/media-upload-url",
    response_model=ApiResponse[RescueMediaUploadUrlResponse],
    dependencies=[Depends(rate_limit("rescue_upload", 10, 60))],
)
async def request_rescue_media_upload_url(
    payload: RescueMediaUploadUrlRequest,
) -> ApiResponse[RescueMediaUploadUrlResponse]:
    """Generate a presigned S3 upload URL for incident photos/videos (max 50MB)."""
    from pawguard.core.exceptions import ValidationFailedError
    from pawguard.services.storage_service import StorageService

    if payload.file_size > 52428800:
        raise ValidationFailedError("File size exceeds the maximum 50MB limit for media evidence.")

    storage = StorageService()
    object_key = storage.build_object_key(folder="rescue", filename=payload.filename)
    upload_url = storage.generate_presigned_upload_url(
        object_key=object_key, content_type=payload.mime_type
    )
    return ApiResponse(
        data=RescueMediaUploadUrlResponse(
            upload_url=upload_url,
            object_key=object_key,
        ),
        message="Presigned upload URL generated successfully.",
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
        severity=payload.severity,
        is_urgent=payload.is_urgent,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return _masked_rescue_response(
        rescue,
        current_user,
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
        assigned_agent_ids=payload.assigned_agent_ids,
        vehicle_id=payload.vehicle_id,
        assigned_vehicle_id=payload.assigned_vehicle_id,
        equipment_details=payload.equipment_details,
        escalation_type=payload.escalation_type,
        escalation_notes=payload.escalation_notes,
        notes=payload.notes,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return _masked_rescue_response(
        rescue,
        current_user,
        message="Rescue vehicle and team dispatched successfully.",
    )


@router.patch(
    "/dispatches/{dispatch_id}",
    response_model=ApiResponse[RescueDispatchResponse],
    dependencies=[Depends(require_permission("rescue:dispatch"))],
)
@router.patch(
    "/dispatch/{dispatch_id}",
    response_model=ApiResponse[RescueDispatchResponse],
    dependencies=[Depends(require_permission("rescue:dispatch"))],
)
async def update_dispatch(
    dispatch_id: uuid.UUID,
    payload: RescueDispatchUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueDispatchResponse]:
    dispatch = await service.update_dispatch(
        dispatch_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RescueDispatchResponse.model_validate(dispatch),
        message="Rescue dispatch updated successfully.",
    )


@router.delete(
    "/dispatches/{dispatch_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("rescue:delete"))],
)
@router.delete(
    "/dispatch/{dispatch_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("rescue:delete"))],
)
async def delete_dispatch(
    dispatch_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[None]:
    await service.delete_dispatch(
        dispatch_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(message="Rescue dispatch deleted successfully.")


@router.post(
    "/{request_id}/escalate",
    response_model=ApiResponse[RescueRequestResponse],
    dependencies=[Depends(require_permission("rescue:update"))],
)
async def escalate_rescue(
    request_id: uuid.UUID,
    payload: RescueEscalateCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    rescue = await service.escalate(
        request_id,
        escalation_type=payload.escalation_type,
        escalation_notes=payload.escalation_notes,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return _masked_rescue_response(
        rescue,
        current_user,
        message="Rescue case escalated successfully.",
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
    return _masked_rescue_response(
        rescue,
        current_user,
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
    return _masked_rescue_response(
        rescue,
        current_user,
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
    return _masked_rescue_response(
        rescue,
        current_user,
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
    return _masked_rescue_response(
        rescue,
        current_user,
        message="Rescue operation marked failed.",
    )


@router.get(
    "/status",
    response_model=ApiResponse[PublicRescueStatusResponse],
    # Public "my submitted case" lookup (PRR 3.2) - no auth, rate-limited.
    # Declared BEFORE /{request_id} so the UUID path converter cannot shadow it.
    dependencies=[Depends(rate_limit("rescue_status_lookup", 10, 60))],
)
async def get_public_status(
    ticket_number: str = Query(..., min_length=1, max_length=64),
    phone: str = Query(..., min_length=1, max_length=32),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[PublicRescueStatusResponse]:
    status = await service.lookup_public_status(ticket_number, phone)
    return ApiResponse(data=status, message="Rescue case status retrieved.")


@router.get(
    "/dispatches",
    response_model=PaginatedResponse[RescueDispatchResponse],
    dependencies=[Depends(require_permission("rescue:read"))],
)
async def list_dispatches(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    service: RescueService = Depends(get_rescue_service),
) -> PaginatedResponse[RescueDispatchResponse]:
    result = await service.list_dispatches_paginated(page=page, sort=sort)
    return result


@router.get(
    "/{request_id}",
    response_model=ApiResponse[RescueRequestResponse],
)
async def get_request(
    request_id: uuid.UUID,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> ApiResponse[RescueRequestResponse]:
    request = await service.get_request(request_id)
    data = _mask_reporter_pii(
        RescueRequestResponse.model_validate(request), current_user
    )
    return ApiResponse(data=data)


@router.get(
    "",
    response_model=PaginatedResponse[RescueRequestResponse],
)
async def list_requests(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(
        None, description="Search by ticket number, reporter name, phone, or location"
    ),
    status: RescueStatus | None = Query(None, description="Filter by status"),
    severity: RescueSeverity | None = Query(None, description="Filter by severity"),
    urgent_only: bool | None = Query(
        None, description="Filter to urgent-flagged cases (PRR 3.1.1)"
    ),
    assigned_to_me: bool | None = Query(
        None, description="Filter to requests assigned to the current user"
    ),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: RescueService = Depends(get_rescue_service),
) -> PaginatedResponse[RescueRequestResponse]:
    result = await service.list_requests_paginated(
        page=page, sort=sort, search_term=search, status=status,
        severity=severity, urgent_only=urgent_only,
        assigned_to_me=current_user.id if (assigned_to_me and current_user) else None,
    )
    data = [_mask_reporter_pii(item, current_user) for item in result.data]
    return PaginatedResponse(data=data, meta=result.meta)



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
