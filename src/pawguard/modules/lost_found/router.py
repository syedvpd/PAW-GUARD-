"""API router for the Lost & Found module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import ForbiddenError
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import get_current_user, CurrentUser
from pawguard.modules.auth.models import User
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.lost_found.models import MatchStatus, ReportStatus
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.lost_found.schemas import (
    FoundReportCreate,
    FoundReportResponse,
    LostReportCreate,
    LostReportResponse,
    ReportMatchResponse,
)
from pawguard.modules.lost_found.service import LostFoundService

router = APIRouter(prefix="/lost-found", tags=["lost-found"])


def get_lost_found_service(db: AsyncSession = Depends(get_db)) -> LostFoundService:
    repo = LostFoundRepository(db)
    return LostFoundService(repo)


@router.post(
    "/lost",
    response_model=ApiResponse[LostReportResponse],
    status_code=status.HTTP_201_CREATED,
)
async def report_lost_pet(
    payload: LostReportCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[LostReportResponse]:
    report = await service.report_lost_pet(current_user.user.id, payload)
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
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[FoundReportResponse]:
    report = await service.report_found_pet(current_user.user.id, payload)
    return ApiResponse(
        data=FoundReportResponse.model_validate(report),
        message="Found roaming animal report registered successfully.",
    )


@router.get(
    "/lost",
    response_model=ApiResponse[list[LostReportResponse]],
    dependencies=[Depends(require_permission("public:read"))],
)
async def list_lost_reports(
    status: ReportStatus | None = None,
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[list[LostReportResponse]]:
    reports = await service._repo.list_lost_reports(status)
    return ApiResponse(data=[LostReportResponse.model_validate(r) for r in reports])


@router.get(
    "/found",
    response_model=ApiResponse[list[FoundReportResponse]],
    dependencies=[Depends(require_permission("public:read"))],
)
async def list_found_reports(
    status: ReportStatus | None = None,
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[list[FoundReportResponse]]:
    reports = await service._repo.list_found_reports(status)
    return ApiResponse(data=[FoundReportResponse.model_validate(r) for r in reports])


@router.get(
    "/lost/{report_id}/matches",
    response_model=ApiResponse[list[ReportMatchResponse]],
)
async def get_matches_for_lost(
    report_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[list[ReportMatchResponse]]:
    report = await service._repo.get_lost_report_by_id(report_id)
    if report is None:
        raise NotFoundError("Lost report not found.")

    user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
    if report.user_id != current_user.user.id and "public:read" not in user_permissions:
        raise ForbiddenError("You do not have permission to view matches for this report.")

    matches = await service.get_matches_for_lost(report_id)
    return ApiResponse(data=[ReportMatchResponse.model_validate(m) for m in matches])


@router.post(
    "/matches/{match_id}/resolve",
    response_model=ApiResponse[ReportMatchResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def resolve_match(
    match_id: uuid.UUID,
    approve: bool,
    service: LostFoundService = Depends(get_lost_found_service),
) -> ApiResponse[ReportMatchResponse]:
    status_val = MatchStatus.CONFIRMED if approve else MatchStatus.REJECTED
    match = await service.update_match_status(match_id, status_val)

    if approve:
        # Also mark reports as resolved
        await service.resolve_lost_report(match.lost_report_id)
        await service.resolve_found_report(match.found_report_id)

    return ApiResponse(
        data=ReportMatchResponse.model_validate(match),
        message="Ownership match resolution recorded.",
    )
