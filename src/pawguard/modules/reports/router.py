from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.reports.schemas import ReportFormat, ReportRequest, ReportResponse, ReportType
from pawguard.modules.reports.service import ReportService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/reports", tags=["reports"])


def get_report_service(
    db: AsyncSession = Depends(get_db),
) -> ReportService:
    return ReportService(db)


@router.post(
    "/generate",
    response_model=ApiResponse[ReportResponse],
    dependencies=[Depends(require_permission("reports:create"))],
)
async def generate_report(
    payload: ReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[ReportResponse]:
    result = await service.generate_report(
        report_type=payload.report_type,
        fmt=payload.format,
        period_start=payload.period_start,
        period_end=payload.period_end,
        filters=payload.filters,
    )
    return ApiResponse(
        data=ReportResponse(**result),
        message=f"{payload.report_type.value} report generated.",
    )


@router.get(
    "/types",
    response_model=ApiResponse[list[str]],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_report_types(
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[list[str]]:
    return ApiResponse(data=[t.value for t in ReportType])


@router.get(
    "/formats",
    response_model=ApiResponse[list[str]],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_report_formats(
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[list[str]]:
    return ApiResponse(data=[f.value for f in ReportFormat])


@router.get(
    "/download/{filename}",
    dependencies=[Depends(require_permission("reports:read"))],
)
async def download_report(
    filename: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> RedirectResponse:
    # 1. Audit log
    await audit.record(
        event_type=AuthAuditEventType.REPORT_DOWNLOADED,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"filename": filename},
    )

    # 2. Get S3 Service & Generate Presigned Download URL
    from pawguard.services.storage_service import get_storage_service

    s3 = get_storage_service()

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    media_types = {
        "pdf": "application/pdf",
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    presigned_url = s3.generate_presigned_download_url(
        object_key=f"reports/{filename}",
        filename=filename,
        content_type=media_type,
        expires_in=900,  # 15 minutes
    )

    return RedirectResponse(url=presigned_url, status_code=307)
