"""API router for the Lost & Found module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Annotated

from arq import ArqRedis
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import BulkDeleteRequest, BulkDeleteResponse
from pawguard.core.exceptions import ForbiddenError, NotFoundError
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
from pawguard.modules.auth.rbac import is_admin_role, require_permission
from pawguard.modules.lost_found.models import MatchStatus, ReportStatus, Species
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.lost_found.schemas import (
    FoundReportCreate,
    FoundReportResponse,
    LostReportCreate,
    LostReportResponse,
    OwnershipClaimReview,
    OwnershipClaimSubmit,
    PetSightingCreate,
    PetSightingResponse,
    ReportMatchResponse,
)
from pawguard.modules.lost_found.service import LostFoundService
from pawguard.modules.notifications.router import get_notification_service
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.portal.router import get_portal_service
from pawguard.modules.portal.schemas import SuccessStoryResponse
from pawguard.modules.portal.service import PortalService
from pawguard.services.audit_service import AuditService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/lost-found", tags=["lost-found"])


def _mask_reporter_identity(
    item: LostReportResponse | FoundReportResponse,
    current_user: CurrentUser | None,
) -> None:
    """Masks the reporter's identity (email + full name + phone) for anyone
    who isn't the reporter or an admin.

    Anonymous visitors (current_user is None) always get the masked view;
    unmasked contact details are only released to the report owner or through
    the claim-verification workflow.
    """
    if item.user is None:
        return
    if current_user is not None and item.user_id == current_user.id:
        return
    if current_user is not None:
        user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
        if "system:admin" in user_permissions:
            return
    # Mask reporter identity (email + name + phone) per PRR §6.1 - the public
    # listing must not expose reporter PII to anonymous visitors or non-owner staff.
    item.user = item.user.model_copy(
        update={
            "email": mask_email(item.user.email),
            "full_name": mask_full_name(item.user.full_name),
            "phone": mask_phone(item.user.phone),
        }
    )


def get_lost_found_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    arq_pool: ArqRedis = Depends(get_arq_pool),
    notification_svc: NotificationService = Depends(get_notification_service),
) -> LostFoundService:
    repo = LostFoundRepository(db)
    return LostFoundService(
        repo, audit_service=audit, arq_pool=arq_pool, notification_service=notification_svc
    )


@router.post(
    "/sighting",
    response_model=ApiResponse[PetSightingResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Public submission of a lost pet sighting by a QR-scanner citizen",
)
@router.post(
    "/found/sighting",
    response_model=ApiResponse[PetSightingResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Public submission of a lost pet sighting by a QR-scanner citizen (alias)",
)
async def report_public_sighting(
    payload: PetSightingCreate,
    request: Request,
    _: Annotated[None, Depends(rate_limit("sighting_report", 10, 60))] = None,
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[PetSightingResponse]:
    ip = request.client.host if request.client else None
    sighting = await service.record_public_sighting(payload, ip_address=ip)
    return ApiResponse(
        data=PetSightingResponse.model_validate(sighting),
        message="Sighting report submitted. The pet owner has been notified.",
    )


@router.post(
    "/lost",
    response_model=ApiResponse[LostReportResponse],
    status_code=status.HTTP_201_CREATED,
)
async def report_lost_pet(
    payload: LostReportCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(rate_limit("lost_report", 10, 60))] = None,
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[LostReportResponse]:
    ip = request.client.host if request.client else None
    report = await service.report_lost_pet(
        current_user.user.id, payload, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=LostReportResponse.model_validate(report),
        message="Lost pet report registered successfully.",
    )


@router.post(
    "/lost/{report_id}/broadcast",
    response_model=ApiResponse[dict[str, object]],
    dependencies=[
        Depends(require_permission("lost_found:broadcast")),
        Depends(rate_limit("lost_alert_broadcast", 3, 3600)),
    ],
)
async def broadcast_lost_pet_alert(
    report_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[dict[str, object]]:
    result = await service.queue_lost_alert_broadcast(
        report_id,
        current_user.id,
        is_admin=is_admin_role(current_user.claims),
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(data=result, message="Lost-pet broadcast queued for delivery.")


@router.post(
    "/found",
    response_model=ApiResponse[FoundReportResponse],
    status_code=status.HTTP_201_CREATED,
)
async def report_found_pet(
    payload: FoundReportCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(rate_limit("found_report", 10, 60))] = None,
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[FoundReportResponse]:
    ip = request.client.host if request.client else None
    report = await service.report_found_pet(
        current_user.user.id, payload, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=FoundReportResponse.model_validate(report),
        message="Found roaming animal report registered successfully.",
    )


@router.get(
    "/lost",
    response_model=PaginatedResponse[LostReportResponse],
)
async def list_lost_reports(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    status: ReportStatus | None = Query(
        ReportStatus.ACTIVE,
        description="Filter by status. Defaults to ACTIVE so resolved/reunited "
        "and expired reports stay off the public lost-pet board.",
    ),
    species: Species | None = None,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> PaginatedResponse[LostReportResponse]:
    result = await service.list_lost_reports_paginated(
        page, sort, search_term=search, status=status, species=species,
    )
    data = [LostReportResponse.model_validate(r) for r in result.data]
    for item in data:
        _mask_reporter_identity(item, current_user)
    return PaginatedResponse(data=data, meta=result.meta)


@router.get(
    "/found",
    response_model=PaginatedResponse[FoundReportResponse],
)
async def list_found_reports(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    status: ReportStatus | None = Query(
        ReportStatus.ACTIVE,
        description="Filter by status. Defaults to ACTIVE so resolved/reunited "
        "and expired reports stay off the public found-pet board.",
    ),
    species: Species | None = None,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> PaginatedResponse[FoundReportResponse]:
    result = await service.list_found_reports_paginated(
        page, sort, search_term=search, status=status, species=species,
    )
    data = [FoundReportResponse.model_validate(r) for r in result.data]
    for item in data:
        _mask_reporter_identity(item, current_user)
    return PaginatedResponse(data=data, meta=result.meta)


@router.get(
    "/reunion-stories",
    response_model=ApiResponse[list[SuccessStoryResponse]],
)
@router.get(
    "/stories",
    response_model=ApiResponse[list[SuccessStoryResponse]],
)
async def get_reunion_stories(
    portal_service: PortalService = Depends(get_portal_service),
) -> ApiResponse[list[SuccessStoryResponse]]:
    stories = await portal_service.list_stories(published_only=True)
    return ApiResponse(data=[SuccessStoryResponse.model_validate(s) for s in stories])


@router.get(
    "/lost/{report_id}",
    response_model=ApiResponse[LostReportResponse],
)
async def get_lost_report(
    report_id: uuid.UUID,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[LostReportResponse]:
    report = await service._repo.get_lost_report_by_id(report_id)
    if report is None:
        raise NotFoundError("Lost report not found.")
    item = LostReportResponse.model_validate(report)
    _mask_reporter_identity(item, current_user)
    return ApiResponse(data=item)


@router.get(
    "/found/{report_id}",
    response_model=ApiResponse[FoundReportResponse],
)
async def get_found_report(
    report_id: uuid.UUID,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[FoundReportResponse]:
    report = await service._repo.get_found_report_by_id(report_id)
    if report is None:
        raise NotFoundError("Found report not found.")
    item = FoundReportResponse.model_validate(report)
    _mask_reporter_identity(item, current_user)
    return ApiResponse(data=item)



@router.get(
    "/lost/{report_id}/matches",
    response_model=PaginatedResponse[ReportMatchResponse],
)
async def get_matches_for_lost(
    report_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> PaginatedResponse[ReportMatchResponse]:
    report = await service._repo.get_lost_report_by_id(report_id)
    if report is None:
        raise NotFoundError("Lost report not found.")

    user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
    if report.user_id != current_user.user.id and "public:read" not in user_permissions:
        raise ForbiddenError("You do not have permission to view matches for this report.")

    result = await service.list_matches_paginated(page, sort, lost_report_id=report_id)
    data = [ReportMatchResponse.model_validate(m) for m in result.data]
    for match in data:
        if match.lost_report is not None:
            _mask_reporter_identity(match.lost_report, current_user)
        if match.found_report is not None:
            _mask_reporter_identity(match.found_report, current_user)
    return PaginatedResponse(data=data, meta=result.meta)


@router.get(
    "/found/{report_id}/matches",
    response_model=PaginatedResponse[ReportMatchResponse],
)
async def get_matches_for_found(
    report_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> PaginatedResponse[ReportMatchResponse]:
    report = await service._repo.get_found_report_by_id(report_id)
    if report is None:
        raise NotFoundError("Found report not found.")

    user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
    if report.user_id != current_user.user.id and "public:read" not in user_permissions:
        raise ForbiddenError("You do not have permission to view matches for this report.")

    result = await service.list_matches_paginated(page, sort, found_report_id=report_id)
    data = [ReportMatchResponse.model_validate(m) for m in result.data]
    for match in data:
        if match.lost_report is not None:
            _mask_reporter_identity(match.lost_report, current_user)
        if match.found_report is not None:
            _mask_reporter_identity(match.found_report, current_user)
    return PaginatedResponse(data=data, meta=result.meta)


@router.post(
    "/matches/{match_id}/claim",
    response_model=ApiResponse[ReportMatchResponse],
)
async def submit_ownership_claim(
    match_id: uuid.UUID,
    payload: OwnershipClaimSubmit,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(rate_limit("ownership_claim", 5, 3600))] = None,
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[ReportMatchResponse]:
    """A potential owner submits verification documents against a match. Only
    the reporters of either side of the match may claim it (PRR 3.10)."""
    ip = request.client.host if request.client else None
    match = await service.submit_ownership_claim(
        match_id,
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=ReportMatchResponse.model_validate(match),
        message="Ownership claim submitted for staff verification.",
    )


@router.post(
    "/matches/{match_id}/claim/review",
    response_model=ApiResponse[ReportMatchResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def review_ownership_claim(
    match_id: uuid.UUID,
    payload: OwnershipClaimReview,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[ReportMatchResponse]:
    """Staff verifies a submitted claim. Approval confirms the match and
    resolves both reports; rejection marks the match rejected. The reviewer
    and time are captured in the audit trail."""
    ip = request.client.host if request.client else None
    match = await service.review_ownership_claim(
        match_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=ReportMatchResponse.model_validate(match),
        message="Ownership claim reviewed.",
    )


@router.post(
    "/matches/{match_id}/resolve",
    response_model=ApiResponse[ReportMatchResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def resolve_match(
    match_id: uuid.UUID,
    approve: bool,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[ReportMatchResponse]:
    match = await service.get_match(match_id)
    # When a claim has been submitted, route through the audited claim-review
    # workflow so the reviewer + timestamps are recorded (PRR 3.10).
    if match.claim_submitted_at is not None:
        match = await service.review_ownership_claim(
            match_id,
            OwnershipClaimReview(approve=approve),
            actor_id=current_user.id,
            ip_address=request.client.host if request.client else None,
        )
    else:
        status_val = MatchStatus.CONFIRMED if approve else MatchStatus.REJECTED
        match = await service.update_match_status(match_id, status_val)
        if approve:
            ip_address = request.client.host if request.client else None
            await service.resolve_lost_report(
                match.lost_report_id, actor_id=current_user.id, ip_address=ip_address,
            )
            await service.resolve_found_report(
                match.found_report_id, actor_id=current_user.id, ip_address=ip_address,
            )

    return ApiResponse(
        data=ReportMatchResponse.model_validate(match),
        message="Ownership match resolution recorded.",
    )


@router.delete(
    "/lost/{report_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def delete_lost_report(
    report_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_lost_report(
        report_id, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(message="Lost report deleted.")


@router.delete(
    "/found/{report_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def delete_found_report(
    report_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_found_report(
        report_id, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(message="Found report deleted.")


@router.post(
    "/lost/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def bulk_delete_lost_reports(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> BulkDeleteResponse:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_delete_lost_reports(
        payload.ids, actor_id=current_user.id, ip_address=ip,
    )
    return BulkDeleteResponse(
        message=f"{deleted} lost reports deleted.",
        deleted_count=deleted,
    )


@router.post(
    "/found/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def bulk_delete_found_reports(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> BulkDeleteResponse:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_delete_found_reports(
        payload.ids, actor_id=current_user.id, ip_address=ip,
    )
    return BulkDeleteResponse(
        message=f"{deleted} found reports deleted.",
        deleted_count=deleted,
    )
