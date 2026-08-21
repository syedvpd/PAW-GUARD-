import pathlib

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.reports.renderers import ensure_reports_dir
from pawguard.modules.reports.schemas import ReportFormat, ReportRequest, ReportResponse, ReportType
from pawguard.modules.reports.service import ReportService

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
    current_user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    reports_dir = pathlib.Path(ensure_reports_dir())
    filepath = (reports_dir / filename).resolve()
    if not str(filepath).startswith(str(reports_dir.resolve())):  # noqa: ASYNC240
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Invalid file path.")
    if not filepath.is_file():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Report not found.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    media_types = {
        "pdf": "application/pdf",
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return FileResponse(
        filepath,
        media_type=media_types.get(ext, "application/octet-stream"),
        filename=filename,
    )
