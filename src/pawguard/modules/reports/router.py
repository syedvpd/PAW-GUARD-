import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.reports.models import JobStatus, ReportJob
from pawguard.modules.reports.schemas import (
    InventoryAnalyticsResponse,
    MedicalAnalyticsResponse,
    ReportAnalyticsRequest,
    ReportFormat,
    ReportJobResponse,
    ReportRequest,
    ReportResponse,
    ReportType,
)
from pawguard.modules.reports.service import ReportService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/reports", tags=["reports"])


def get_report_service(
    db: AsyncSession = Depends(get_db),
) -> ReportService:
    return ReportService(db)


@router.get(
    "/inventory/analytics",
    response_model=ApiResponse[InventoryAnalyticsResponse],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_inventory_analytics_report(
    category: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[InventoryAnalyticsResponse]:
    filters = {"category": category} if category else None
    result = await service.get_inventory_analytics(filters=filters)
    return ApiResponse(
        data=InventoryAnalyticsResponse(**result),
        message="Inventory analytics retrieved successfully.",
    )


@router.get(
    "/analytics/inventory",
    response_model=ApiResponse[InventoryAnalyticsResponse],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_inventory_analytics_report_alias(
    category: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[InventoryAnalyticsResponse]:
    filters = {"category": category} if category else None
    result = await service.get_inventory_analytics(filters=filters)
    return ApiResponse(
        data=InventoryAnalyticsResponse(**result),
        message="Inventory analytics retrieved successfully.",
    )


@router.post(
    "/inventory/analytics",
    response_model=ApiResponse[InventoryAnalyticsResponse],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def generate_inventory_analytics_report_post(
    payload: ReportAnalyticsRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[InventoryAnalyticsResponse]:
    filters = payload.filters if payload else None
    result = await service.get_inventory_analytics(filters=filters)
    return ApiResponse(
        data=InventoryAnalyticsResponse(**result),
        message="Inventory analytics retrieved successfully.",
    )


@router.get(
    "/medical/analytics",
    response_model=ApiResponse[MedicalAnalyticsResponse],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_medical_analytics_report(
    current_user: CurrentUser = Depends(get_current_user),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[MedicalAnalyticsResponse]:
    result = await service.get_medical_analytics()
    return ApiResponse(
        data=MedicalAnalyticsResponse(**result),
        message="Medical analytics retrieved successfully.",
    )


@router.get(
    "/analytics/medical",
    response_model=ApiResponse[MedicalAnalyticsResponse],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_medical_analytics_report_alias(
    current_user: CurrentUser = Depends(get_current_user),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[MedicalAnalyticsResponse]:
    result = await service.get_medical_analytics()
    return ApiResponse(
        data=MedicalAnalyticsResponse(**result),
        message="Medical analytics retrieved successfully.",
    )


@router.post(
    "/medical/analytics",
    response_model=ApiResponse[MedicalAnalyticsResponse],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def generate_medical_analytics_report_post(
    payload: ReportAnalyticsRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[MedicalAnalyticsResponse]:
    filters = payload.filters if payload else None
    result = await service.get_medical_analytics(filters=filters)
    return ApiResponse(
        data=MedicalAnalyticsResponse(**result),
        message="Medical analytics retrieved successfully.",
    )


@router.post(
    "/analytics",
    response_model=ApiResponse[InventoryAnalyticsResponse | MedicalAnalyticsResponse],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_report_analytics_post(
    payload: ReportAnalyticsRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[InventoryAnalyticsResponse | MedicalAnalyticsResponse]:
    if payload.report_type == ReportType.MEDICAL:
        result = await service.get_medical_analytics(filters=payload.filters)
        return ApiResponse(
            data=MedicalAnalyticsResponse(**result),
            message="Medical analytics retrieved successfully.",
        )
    result = await service.get_inventory_analytics(filters=payload.filters)
    return ApiResponse(
        data=InventoryAnalyticsResponse(**result),
        message="Report analytics retrieved successfully.",
    )


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


@router.post(
    "/jobs",
    response_model=ApiResponse[ReportJobResponse],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("reports:create"))],
)
async def create_report_job(
    payload: ReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ReportJobResponse]:
    """Creates a ReportJob row and initiates asynchronous background generation."""
    job = ReportJob(
        id=uuid.uuid4(),
        report_type=payload.report_type.value,
        format=payload.format.value,
        status=JobStatus.PENDING.value,
        requester_id=current_user.id,
        filters=payload.filters,
        created_at=datetime.now(UTC),
    )
    db.add(job)
    await db.flush()

    res = ReportJobResponse(
        job_id=job.id,
        report_type=job.report_type,
        format=job.format,
        status=job.status,
        created_at=job.created_at,
        completed_at=None,
        result_object_key=None,
        download_url=None,
        error_message=None,
    )
    return ApiResponse(
        data=res,
        message="Report generation job enqueued.",
    )


async def execute_report_job(job_id: uuid.UUID, db: AsyncSession) -> ReportJob:
    """Executes the report generation pipeline for a given job and updates status to DONE/FAILED."""
    stmt = select(ReportJob).where(ReportJob.id == job_id)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        raise NotFoundError(f"ReportJob {job_id} not found.")

    job.status = JobStatus.RUNNING.value
    await db.flush()

    try:
        service = ReportService(db)
        result = await service.generate_report(
            report_type=ReportType(job.report_type),
            fmt=ReportFormat(job.format),
            filters=job.filters,
        )
        object_key = result.get("download_url", f"reports/{job.id}.{job.format}")
        job.result_object_key = object_key
        job.status = JobStatus.DONE.value
        job.completed_at = datetime.now(UTC)
    except Exception as exc:
        job.status = JobStatus.FAILED.value
        job.error_message = str(exc)
        job.completed_at = datetime.now(UTC)

    await db.flush()
    return job


@router.get(
    "/jobs/{job_id}",
    response_model=ApiResponse[ReportJobResponse],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_report_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ReportJobResponse]:
    """Poll the status of an asynchronous report generation job."""
    stmt = select(ReportJob).where(ReportJob.id == job_id)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        raise NotFoundError(f"Report job {job_id} not found.")

    download_url = None
    if job.status == JobStatus.DONE.value and job.result_object_key:
        download_url = f"/api/v1/reports/jobs/{job.id}/download"

    res = ReportJobResponse(
        job_id=job.id,
        report_type=job.report_type,
        format=job.format,
        status=job.status,
        created_at=job.created_at,
        completed_at=job.completed_at,
        result_object_key=job.result_object_key,
        download_url=download_url,
        error_message=job.error_message,
    )
    return ApiResponse(data=res, message="Report job status retrieved.")


@router.get(
    "/jobs/{job_id}/download",
    dependencies=[Depends(require_permission("reports:read"))],
)
async def download_report_job(
    job_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Download the completed artifact of an asynchronous report job."""
    stmt = select(ReportJob).where(ReportJob.id == job_id)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        raise NotFoundError(f"Report job {job_id} not found.")

    if job.status != JobStatus.DONE.value:
        raise ValidationFailedError(f"Report job is not ready for download (status: {job.status}).")

    if audit:
        await audit.record(
            event_type=AuthAuditEventType.REPORT_DOWNLOADED,
            actor_id=current_user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            metadata={"job_id": str(job.id), "object_key": job.result_object_key},
        )

    from pawguard.services.storage_service import get_storage_service

    s3 = get_storage_service()
    filename = f"report_{job.report_type}_{job.id}.{job.format}"
    object_key = job.result_object_key or f"reports/{filename}"

    media_types = {
        "pdf": "application/pdf",
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    media_type = media_types.get(job.format.lower(), "application/octet-stream")

    presigned_url = s3.generate_presigned_download_url(
        object_key=object_key,
        filename=filename,
        content_type=media_type,
        expires_in=900,
    )
    return RedirectResponse(url=presigned_url, status_code=307)


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
