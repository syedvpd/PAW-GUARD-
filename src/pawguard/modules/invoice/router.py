"""API router for the Invoicing & Service Fee Collection module."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams, build_pagination_meta, page_params
from pawguard.core.payments import PaymentGateway, PaymentGatewayError, get_payment_gateway
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.invoice.models import InvoiceStatus, InvoiceType
from pawguard.modules.invoice.repository import InvoiceRepository
from pawguard.modules.invoice.schemas import (
    InvoiceCancelRequest,
    InvoiceCreate,
    InvoiceResponse,
    InvoiceStatusUpdate,
)
from pawguard.modules.invoice.service import InvoiceService
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService
from pawguard.services.audit_service import AuditService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/invoices", tags=["invoices"])


def get_invoice_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    arq_pool: Any = Depends(get_arq_pool),
) -> InvoiceService:
    repo = InvoiceRepository(db)
    notification_repo = NotificationRepository(db)
    notification_svc = NotificationService(repository=notification_repo, arq_pool=arq_pool)

    gateway: PaymentGateway | None = None
    try:
        gateway = get_payment_gateway()
    except Exception:
        gateway = None

    return InvoiceService(
        repository=repo,
        payment_gateway=gateway,
        audit_service=audit,
        notification_service=notification_svc,
    )


@router.get(
    "",
    response_model=PaginatedResponse[InvoiceResponse],
    dependencies=[
        Depends(
            require_permission(
                "invoices:read",
                "invoicesRead",
                "finance:read",
                "system:admin",
                "rescue_centre:admin",
            )
        )
    ],
    summary="List invoices with filtering and pagination",
)
async def list_invoices(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    status: InvoiceStatus | None = Query(None, description="Filter by invoice status"),
    invoice_type: InvoiceType | None = Query(None, description="Filter by invoice type"),
    billed_user_id: uuid.UUID | None = Query(None, description="Filter by billed user ID"),
    search: str | None = Query(
        None, description="Search by invoice number, org name, or description"
    ),
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    service: InvoiceService = Depends(get_invoice_service),
) -> PaginatedResponse[InvoiceResponse]:
    items, total = await service.list_invoices_paginated(
        page,
        sort,
        status=status,
        invoice_type=invoice_type,
        billed_user_id=billed_user_id,
        search_term=search,
        start_date=start_date,
        end_date=end_date,
    )
    meta = build_pagination_meta(total=total, params=page)
    return PaginatedResponse(
        data=[InvoiceResponse.model_validate(inv) for inv in items],
        meta=meta,
    )


@router.post(
    "",
    response_model=ApiResponse[InvoiceResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_permission(
                "invoices:write",
                "invoicesWrite",
                "finance:write",
                "system:admin",
            )
        )
    ],
    summary="Create a draft invoice",
)
async def create_invoice(
    payload: InvoiceCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InvoiceService = Depends(get_invoice_service),
) -> ApiResponse[InvoiceResponse]:
    ip = request.client.host if request.client else None
    invoice = await service.create_draft_invoice(
        payload,
        creator_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=InvoiceResponse.model_validate(invoice),
        message="Invoice created successfully in draft status.",
    )


@router.get(
    "/{invoice_id}",
    response_model=ApiResponse[InvoiceResponse],
    dependencies=[
        Depends(
            require_permission(
                "invoices:read",
                "invoicesRead",
                "finance:read",
                "system:admin",
                "rescue_centre:admin",
            )
        )
    ],
    summary="Get invoice detail",
)
async def get_invoice(
    invoice_id: uuid.UUID,
    service: InvoiceService = Depends(get_invoice_service),
) -> ApiResponse[InvoiceResponse]:
    invoice = await service.get_invoice(invoice_id)
    return ApiResponse(data=InvoiceResponse.model_validate(invoice))


@router.post(
    "/{invoice_id}/send",
    response_model=ApiResponse[InvoiceResponse],
    dependencies=[
        Depends(
            require_permission(
                "invoices:write",
                "invoicesWrite",
                "finance:write",
                "system:admin",
            )
        )
    ],
    summary="Issue hosted payment link and send invoice to recipient",
)
async def send_invoice(
    invoice_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InvoiceService = Depends(get_invoice_service),
) -> ApiResponse[InvoiceResponse]:
    ip = request.client.host if request.client else None
    invoice = await service.send_invoice(
        invoice_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=InvoiceResponse.model_validate(invoice),
        message="Invoice payment link issued and sent to recipient.",
    )


@router.post(
    "/{invoice_id}/cancel",
    response_model=ApiResponse[InvoiceResponse],
    dependencies=[
        Depends(
            require_permission(
                "invoices:write",
                "invoicesWrite",
                "finance:write",
                "system:admin",
            )
        )
    ],
    summary="Cancel an invoice and void payment link",
)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceCancelRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InvoiceService = Depends(get_invoice_service),
) -> ApiResponse[InvoiceResponse]:
    ip = request.client.host if request.client else None
    invoice = await service.cancel_invoice(
        invoice_id,
        reason=payload.reason,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=InvoiceResponse.model_validate(invoice),
        message="Invoice cancelled successfully.",
    )


@router.post(
    "/{invoice_id}/resend",
    response_model=ApiResponse[InvoiceResponse],
    dependencies=[
        Depends(
            require_permission(
                "invoices:write",
                "invoicesWrite",
                "finance:write",
                "system:admin",
            )
        )
    ],
    summary="Resend payment link to invoice recipient",
)
async def resend_invoice(
    invoice_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InvoiceService = Depends(get_invoice_service),
) -> ApiResponse[InvoiceResponse]:
    ip = request.client.host if request.client else None
    invoice = await service.resend_invoice(
        invoice_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=InvoiceResponse.model_validate(invoice),
        message="Invoice payment link re-sent.",
    )


@router.patch(
    "/{invoice_id}/status",
    response_model=ApiResponse[InvoiceResponse],
    dependencies=[
        Depends(
            require_permission(
                "invoices:write",
                "invoicesWrite",
                "finance:write",
                "system:admin",
            )
        )
    ],
    summary="Manual status override (e.g. offline bank transfer)",
)
async def update_invoice_status(
    invoice_id: uuid.UUID,
    payload: InvoiceStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InvoiceService = Depends(get_invoice_service),
) -> ApiResponse[InvoiceResponse]:
    ip = request.client.host if request.client else None
    invoice = await service.manual_status_update(
        invoice_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=InvoiceResponse.model_validate(invoice),
        message=f"Invoice status updated to {payload.status.value}.",
    )


@router.get(
    "/{invoice_id}/receipt",
    summary="Download formal electronic receipt for a paid invoice",
)
async def download_invoice_receipt(
    invoice_id: uuid.UUID,
    service: InvoiceService = Depends(get_invoice_service),
) -> Response:
    pdf_bytes = await service.generate_receipt_pdf(invoice_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invoice_receipt_{invoice_id}.pdf"},
    )


@router.post(
    "/webhooks/razorpay",
    status_code=status.HTTP_200_OK,
    summary="Razorpay webhook endpoint for payment link events",
)
async def razorpay_invoice_webhook(
    request: Request,
    service: InvoiceService = Depends(get_invoice_service),
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    if not x_razorpay_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Razorpay-Signature header.",
        )

    raw_body = await request.body()
    gateway: PaymentGateway | None = None
    try:
        gateway = get_payment_gateway()
    except Exception:
        return {"status": "ignored"}

    try:
        event = gateway.parse_webhook(payload=raw_body, signature=x_razorpay_signature)
    except PaymentGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    processed = await service.process_webhook(event)
    return {"status": "processed" if processed else "ignored"}
