"""API router for the Lost & Found module. Routers only validate and call services (RULE-004)."""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import BulkDeleteRequest, BulkDeleteResponse
from pawguard.core.exceptions import ForbiddenError, NotFoundError
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.pii import mask_email
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.lost_found.models import MatchStatus, ReportStatus, Species
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.lost_found.schemas import (
    FoundReportCreate,
    FoundReportResponse,
    LostReportCreate,
    LostReportResponse,
    ReportMatchResponse,
)
from pawguard.modules.lost_found.service import LostFoundService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/lost-found", tags=["lost-found"])


def _mask_reporter_email(
    item: LostReportResponse | FoundReportResponse, current_user: CurrentUser
) -> None:
    """Masks the reporter's email for anyone who isn't the reporter or an admin.

    General list/detail views must not leak reporter PII per RULE-006; unmasked
    contact details are only released through the claim-verification workflow.
    """
    if item.user is None or item.user_id == current_user.id:
        return
    user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
    if "system:admin" in user_permissions:
        return
    item.user = item.user.model_copy(update={"email": mask_email(item.user.email)})


def get_lost_found_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> LostFoundService:
    repo = LostFoundRepository(db)
    return LostFoundService(repo, audit_service=audit)


@router.post(
    "/lost",
    response_model=ApiResponse[LostReportResponse],
    status_code=status.HTTP_201_CREATED,
)
async def report_lost_pet(
    payload: LostReportCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
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
    "/found",
    response_model=ApiResponse[FoundReportResponse],
    status_code=status.HTTP_201_CREATED,
)
async def report_found_pet(
    payload: FoundReportCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
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
    dependencies=[Depends(require_permission("public:read"))],
)
async def list_lost_reports(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    status: ReportStatus | None = None,
    species: Species | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> PaginatedResponse[LostReportResponse]:
    result = await service.list_lost_reports_paginated(
        page, sort, search_term=search, status=status, species=species,
    )
    data = [LostReportResponse.model_validate(r) for r in result.data]
    for item in data:
        _mask_reporter_email(item, current_user)
    return PaginatedResponse(data=data, meta=result.meta)


@router.get(
    "/found",
    response_model=PaginatedResponse[FoundReportResponse],
    dependencies=[Depends(require_permission("public:read"))],
)
async def list_found_reports(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    status: ReportStatus | None = None,
    species: Species | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> PaginatedResponse[FoundReportResponse]:
    result = await service.list_found_reports_paginated(
        page, sort, search_term=search, status=status, species=species,
    )
    data = [FoundReportResponse.model_validate(r) for r in result.data]
    for item in data:
        _mask_reporter_email(item, current_user)
    return PaginatedResponse(data=data, meta=result.meta)


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
            _mask_reporter_email(match.lost_report, current_user)
        if match.found_report is not None:
            _mask_reporter_email(match.found_report, current_user)
    return PaginatedResponse(data=data, meta=result.meta)


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
    status_val = MatchStatus.CONFIRMED if approve else MatchStatus.REJECTED
    match = await service.update_match_status(match_id, status_val)

    if approve:
        actor_id = current_user.id
        ip_address = request.client.host if request.client else None
        await service.resolve_lost_report(
            match.lost_report_id, actor_id=actor_id, ip_address=ip_address,
        )
        await service.resolve_found_report(
            match.found_report_id, actor_id=actor_id, ip_address=ip_address,
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
