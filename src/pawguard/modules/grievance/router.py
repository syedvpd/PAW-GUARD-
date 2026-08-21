"""API router for Grievance & Feedback module (RULE-004)."""

import uuid
from typing import Annotated

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
from pawguard.core.rate_limiter import rate_limit
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.grievance.models import GrievanceStatus
from pawguard.modules.grievance.repository import GrievanceRepository
from pawguard.modules.grievance.schemas import (
    CommentCreate,
    CommentResponse,
    GrievanceAssign,
    GrievanceCreate,
    GrievanceEscalate,
    GrievanceListFilter,
    GrievanceResponse,
    GrievanceUpdate,
    ServiceFeedbackCreate,
    ServiceFeedbackResponse,
)
from pawguard.modules.grievance.service import GrievanceService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/grievance", tags=["grievance"])


def get_grievance_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> GrievanceService:
    return GrievanceService(GrievanceRepository(db), audit_service=audit)


@router.post(
    "",
    response_model=ApiResponse[GrievanceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def submit_complaint(
    payload: GrievanceCreate,
    _: Annotated[None, Depends(rate_limit("grievance_submit", 10, 3600))] = None,
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[GrievanceResponse]:
    ticket = await service.submit_complaint(payload)
    return ApiResponse(
        data=GrievanceResponse.model_validate(ticket),
        message="Complaint submitted successfully.",
    )


@router.get(
    "",
    response_model=PaginatedResponse[GrievanceResponse],
    dependencies=[Depends(require_permission("grievance:read"))],
)
async def list_tickets(
    params: PageParams = Depends(page_params),
    status_filter: GrievanceStatus | None = Query(None, alias="status"),
    complaint_type: str | None = Query(None),
    assigned_to: uuid.UUID | None = Query(None, alias="assigned_to"),
    search: str | None = Query(None),
    service: GrievanceService = Depends(get_grievance_service),
) -> PaginatedResponse[GrievanceResponse]:
    filter_params = GrievanceListFilter(
        status=status_filter,
        complaint_type=complaint_type,
        assigned_to_admin_id=assigned_to,
        search=search,
    )
    tickets, meta = await service.list_tickets(page_params=params, filter_params=filter_params)
    return PaginatedResponse(
        data=[GrievanceResponse.model_validate(t) for t in tickets],
        meta=meta,
    )


@router.get(
    "/feedback",
    response_model=PaginatedResponse[ServiceFeedbackResponse],
    dependencies=[Depends(require_permission("grievance:read"))],
)
async def list_feedback(
    params: PageParams = Depends(page_params),
    service: GrievanceService = Depends(get_grievance_service),
) -> PaginatedResponse[ServiceFeedbackResponse]:
    feedback, meta = await service.list_feedback(page_params=params)
    return PaginatedResponse(
        data=[ServiceFeedbackResponse.model_validate(f) for f in feedback],
        meta=meta,
    )


@router.get(
    "/{ticket_id}",
    response_model=ApiResponse[GrievanceResponse],
    dependencies=[Depends(require_permission("grievance:read"))],
)
async def get_ticket(
    ticket_id: uuid.UUID,
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[GrievanceResponse]:
    ticket = await service.get_ticket(ticket_id)
    return ApiResponse(data=GrievanceResponse.model_validate(ticket))


@router.put(
    "/{ticket_id}",
    response_model=ApiResponse[GrievanceResponse],
    dependencies=[Depends(require_permission("grievance:update"))],
)
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: GrievanceUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[GrievanceResponse]:
    ticket = await service.update_ticket(
        ticket_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=GrievanceResponse.model_validate(ticket),
        message="Ticket updated.",
    )


@router.patch(
    "/{ticket_id}/status",
    response_model=ApiResponse[GrievanceResponse],
    dependencies=[Depends(require_permission("grievance:update"))],
)
async def update_ticket_status(
    ticket_id: uuid.UUID,
    status: GrievanceStatus,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[GrievanceResponse]:
    ticket = await service.update_ticket_status(
        ticket_id,
        status,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=GrievanceResponse.model_validate(ticket),
        message=f"Ticket status updated to {status}.",
    )


@router.post(
    "/{ticket_id}/assign",
    response_model=ApiResponse[GrievanceResponse],
    dependencies=[Depends(require_permission("grievance:assign"))],
)
async def assign_ticket(
    ticket_id: uuid.UUID,
    payload: GrievanceAssign,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[GrievanceResponse]:
    ticket = await service.assign_ticket(
        ticket_id,
        payload.assigned_to_admin_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=GrievanceResponse.model_validate(ticket),
        message="Ticket assigned.",
    )


@router.post(
    "/{ticket_id}/escalate",
    response_model=ApiResponse[GrievanceResponse],
    dependencies=[Depends(require_permission("grievance:assign"))],
)
async def escalate_ticket(
    ticket_id: uuid.UUID,
    payload: GrievanceEscalate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[GrievanceResponse]:
    ticket = await service.escalate_ticket(
        ticket_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=GrievanceResponse.model_validate(ticket),
        message="Ticket escalated.",
    )


@router.post(
    "/{ticket_id}/comments",
    response_model=ApiResponse[CommentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("grievance:comment"))],
)
async def add_comment(
    ticket_id: uuid.UUID,
    payload: CommentCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[CommentResponse]:
    comment = await service.add_comment(ticket_id, payload, author_id=current_user.id)
    return ApiResponse(
        data=CommentResponse.model_validate(comment),
        message="Comment added.",
    )


@router.get(
    "/{ticket_id}/comments",
    response_model=ApiResponse[list[CommentResponse]],
    dependencies=[Depends(require_permission("grievance:read"))],
)
async def list_comments(
    ticket_id: uuid.UUID,
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[list[CommentResponse]]:
    comments = await service.list_comments(ticket_id)
    return ApiResponse(data=[CommentResponse.model_validate(c) for c in comments])


@router.post(
    "/feedback",
    response_model=ApiResponse[ServiceFeedbackResponse],
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    payload: ServiceFeedbackCreate,
    _: Annotated[None, Depends(rate_limit("grievance_feedback", 10, 3600))] = None,
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[ServiceFeedbackResponse]:
    fb = await service.submit_feedback(payload)
    return ApiResponse(
        data=ServiceFeedbackResponse.model_validate(fb),
        message="Feedback submitted.",
    )


@router.delete(
    "/{ticket_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("grievance:update"))],
)
async def soft_delete_ticket(
    ticket_id: uuid.UUID,
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[None]:
    await service.soft_delete_ticket(ticket_id)
    return ApiResponse(message="Grievance ticket deleted.")


@router.delete(
    "/feedback/{feedback_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("grievance:update"))],
)
async def soft_delete_feedback(
    feedback_id: uuid.UUID,
    service: GrievanceService = Depends(get_grievance_service),
) -> ApiResponse[None]:
    await service.soft_delete_feedback(feedback_id)
    return ApiResponse(message="Feedback deleted.")


@router.post(
    "/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("grievance:update"))],
)
async def bulk_delete_tickets(
    payload: BulkDeleteRequest,
    service: GrievanceService = Depends(get_grievance_service),
) -> BulkDeleteResponse:
    deleted = await service.bulk_delete_tickets(payload.ids)
    return BulkDeleteResponse(
        message=f"{deleted} grievance ticket(s) deleted.",
        deleted_count=deleted,
    )


@router.post(
    "/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("grievance:update"))],
)
async def bulk_update_ticket_status(
    payload: BulkStatusUpdateRequest,
    service: GrievanceService = Depends(get_grievance_service),
) -> BulkStatusUpdateResponse:
    status = parse_enum(GrievanceStatus, payload.status)
    updated = await service.bulk_update_ticket_status(payload.ids, status)
    return BulkStatusUpdateResponse(
        message=f"{updated} grievance ticket(s) updated.",
        updated_count=updated,
    )


@router.post(
    "/feedback/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("grievance:update"))],
)
async def bulk_delete_feedback(
    payload: BulkDeleteRequest,
    service: GrievanceService = Depends(get_grievance_service),
) -> BulkDeleteResponse:
    deleted = await service.bulk_delete_feedback(payload.ids)
    return BulkDeleteResponse(
        message=f"{deleted} feedback(s) deleted.",
        deleted_count=deleted,
    )
