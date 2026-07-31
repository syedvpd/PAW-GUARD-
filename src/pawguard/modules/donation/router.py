"""API router for the Donation Management module.

Routers only validate and call services (RULE-004).
"""

import contextlib
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.exceptions import ValidationFailedError, parse_enum
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.payments import PaymentGatewayError, get_payment_gateway
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.donation.models import DonationStatus, DonationType, SponsorshipStatus
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.schemas import (
    DonationCreate,
    DonationOrderResponse,
    DonationResponse,
    DonationStatusUpdate,
    DonationVerifyRequest,
    DonorProfileCreate,
    DonorProfileResponse,
    DonorProfileUpdate,
    SponsorshipCreate,
    SponsorshipResponse,
    SponsorshipStatusUpdate,
)
from pawguard.modules.donation.service import DonationService
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.storage.schemas import DownloadUrlResponse
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService

router = APIRouter(prefix="/donations", tags=["donations"])


def get_donation_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> DonationService:
    repo = DonationRepository(db)
    dog_repo = DogRepository(db)
    notification_repo = NotificationRepository(db)
    notification_svc = NotificationService(repository=notification_repo)
    storage_svc = StorageService()
    try:
        gateway = get_payment_gateway()
    except PaymentGatewayError:
        gateway = None
    return DonationService(
        repo, dog_repo, gateway, audit_service=audit,
        notification_service=notification_svc,
        storage_service=storage_svc,
    )


@router.post(
    "/register",
    response_model=ApiResponse[DonorProfileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register_donor(
    payload: DonorProfileCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonorProfileResponse]:
    donor = await service.register_donor(current_user.id, payload)
    return ApiResponse(
        data=DonorProfileResponse.model_validate(donor),
        message="Donor profile registered successfully.",
    )


@router.put(
    "/donors/{donor_id}",
    response_model=ApiResponse[DonorProfileResponse],
    dependencies=[Depends(require_permission("donation:update"))],
)
async def update_donor(
    donor_id: uuid.UUID,
    payload: DonorProfileUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonorProfileResponse]:
    donor = await service.update_donor(
        donor_id, payload, actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=DonorProfileResponse.model_validate(donor),
        message="Donor profile updated successfully.",
    )


@router.delete(
    "/donors/{donor_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("donation:update"))],
)
async def soft_delete_donor(
    donor_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[None]:
    await service.soft_delete_donor(
        donor_id, actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(message="Donor profile deleted successfully.")


@router.post(
    "",
    response_model=ApiResponse[DonationResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("donation:manage"))],
)
async def record_manual_donation(
    payload: DonationCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationResponse]:
    """Records an already-collected offline donation (cash, bank transfer,
    etc.) without going through a payment gateway. Staff-only: online
    donations from the public must use POST /donations/checkout + /verify,
    which actually verify payment before marking a donation SUCCESS."""
    donation = await service.make_donation(
        current_user.id, payload, actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=DonationResponse.model_validate(donation),
        message="Donation recorded successfully.",
    )


@router.post(
    "/checkout",
    response_model=ApiResponse[DonationOrderResponse],
    status_code=status.HTTP_201_CREATED,
)
async def initiate_donation_checkout(
    payload: DonationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationOrderResponse]:
    """Create a PENDING donation plus a payment-provider order. The client
    opens the provider's checkout with the returned order details, then calls
    `/donations/verify` once the user completes payment."""
    order = await service.initiate_online_donation(current_user.id, payload)
    return ApiResponse(data=order, message="Donation order created. Complete payment to confirm.")


@router.post(
    "/verify",
    response_model=ApiResponse[DonationResponse],
)
async def verify_donation_checkout(
    payload: DonationVerifyRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationResponse]:
    donation = await service.verify_donation_payment(
        donation_id=payload.donation_id,
        gateway_order_id=payload.gateway_order_id,
        gateway_payment_id=payload.gateway_payment_id,
        gateway_signature=payload.gateway_signature,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=DonationResponse.model_validate(donation),
        message="Thank you! Donation confirmed.",
    )


@router.post(
    "/webhook/razorpay",
    response_model=ApiResponse[None],
    include_in_schema=False,
)
async def razorpay_webhook(
    request: Request,
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[None]:
    """Server-to-server confirmation from Razorpay. Not authenticated with a
    user session - verified instead via the webhook signature header."""
    signature = request.headers.get("X-Razorpay-Signature", "")
    body = await request.body()
    # Swallow signature/config errors here so Razorpay doesn't retry a request
    # that will never succeed; real failures are logged upstream.
    with contextlib.suppress(ValidationFailedError):
        await service.handle_gateway_webhook(body, signature)
    return ApiResponse(message="ok")


@router.get(
    "/history",
    response_model=ApiResponse[list[DonationResponse]],
)
async def get_donation_history(
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[list[DonationResponse]]:
    history = await service.list_donations_for_user(current_user.id)
    return ApiResponse(data=[DonationResponse.model_validate(h) for h in history])


@router.get(
    "",
    response_model=PaginatedResponse[DonationResponse],
    dependencies=[Depends(require_permission("donation:read"))],
)
async def list_all_donations(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by transaction_id, notes"),
    donation_type: DonationType | None = Query(None, description="Filter by donation type"),
    status: DonationStatus | None = Query(None, description="Filter by status"),
    date_from: str | None = Query(None, description="Filter from date (ISO format)"),
    date_to: str | None = Query(None, description="Filter to date (ISO format)"),
    service: DonationService = Depends(get_donation_service),
) -> PaginatedResponse[DonationResponse]:
    return await service.list_donations_paginated(
        page=page,
        sort=sort,
        search_term=search,
        donation_type=donation_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/donors",
    response_model=PaginatedResponse[DonorProfileResponse],
    dependencies=[Depends(require_permission("donation:read"))],
)
async def list_donors(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search donor profiles"),
    service: DonationService = Depends(get_donation_service),
) -> PaginatedResponse[DonorProfileResponse]:
    return await service.list_donors_paginated(
        page=page,
        sort=sort,
        search_term=search,
    )


@router.get(
    "/{donation_id}/receipt",
    response_model=ApiResponse[DownloadUrlResponse],
)
async def get_donation_receipt(
    donation_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DownloadUrlResponse]:
    donation = await service.get_donation(donation_id)
    user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
    if donation.donor_id != current_user.user.id and "donation:read" not in user_permissions:
        from pawguard.core.exceptions import ForbiddenError
        raise ForbiddenError("You do not have permission to view this receipt.")
    if not donation.receipt_file_key:
        from pawguard.core.exceptions import NotFoundError
        raise NotFoundError("Receipt not yet generated for this donation.")
    storage = StorageService()
    download_url = storage.generate_presigned_download_url(object_key=donation.receipt_file_key)
    return ApiResponse(
        data=DownloadUrlResponse(
            download_url=download_url,
            object_key=donation.receipt_file_key,
            file_id=donation.id,
        ),
    )


@router.patch(
    "/{donation_id}/status",
    response_model=ApiResponse[DonationResponse],
    dependencies=[Depends(require_permission("donation:update"))],
)
async def update_donation_status(
    donation_id: uuid.UUID,
    payload: DonationStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationResponse]:
    donation = await service.update_donation_status(
        donation_id, payload.status, actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=DonationResponse.model_validate(donation),
        message="Donation status updated successfully.",
    )


@router.post(
    "/bulk/status-update",
    response_model=ApiResponse[BulkStatusUpdateResponse],
    dependencies=[Depends(require_permission("donation:update"))],
)
async def bulk_update_donation_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[BulkStatusUpdateResponse]:
    updated = await service.bulk_update_status(
        payload.ids,
        parse_enum(DonationStatus, payload.status),
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkStatusUpdateResponse(
            message=f"{updated} donation(s) status updated.",
            updated_count=updated,
        ),
    )


@router.post(
    "/donors/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("donation:update"))],
)
async def bulk_delete_donors(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[BulkDeleteResponse]:
    deleted = await service.bulk_soft_delete(
        payload.ids, actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} donor(s) deleted.",
            deleted_count=deleted,
        ),
    )


@router.post(
    "/sponsorships",
    response_model=ApiResponse[SponsorshipResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_sponsorship(
    payload: SponsorshipCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[SponsorshipResponse]:
    sponsorship = await service.create_sponsorship(
        current_user.id, payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=SponsorshipResponse.model_validate(sponsorship),
        message="Sponsorship created successfully.",
    )


@router.patch(
    "/sponsorships/{sponsorship_id}/status",
    response_model=ApiResponse[SponsorshipResponse],
)
async def update_sponsorship_status(
    sponsorship_id: uuid.UUID,
    payload: SponsorshipStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[SponsorshipResponse]:
    if payload.status == SponsorshipStatus.PAUSED:
        sponsorship = await service.pause_sponsorship(
            sponsorship_id, actor_id=current_user.id,
            ip_address=request.client.host if request.client else None,
        )
        message = "Sponsorship paused successfully."
    elif payload.status == SponsorshipStatus.CANCELLED:
        sponsorship = await service.cancel_sponsorship(
            sponsorship_id, actor_id=current_user.id,
            ip_address=request.client.host if request.client else None,
        )
        message = "Sponsorship cancelled successfully."
    else:
        raise ValidationFailedError(
            f"Cannot transition to {payload.status.value} via this endpoint."
        )

    return ApiResponse(
        data=SponsorshipResponse.model_validate(sponsorship),
        message=message,
    )


@router.get(
    "/sponsorships/my",
    response_model=ApiResponse[list[SponsorshipResponse]],
)
async def list_my_sponsorships(
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[list[SponsorshipResponse]]:
    sponsorships = await service.list_sponsorships_for_donor(current_user.id)
    return ApiResponse(data=[SponsorshipResponse.model_validate(s) for s in sponsorships])


@router.get(
    "/sponsorships",
    response_model=ApiResponse[list[SponsorshipResponse]],
    dependencies=[Depends(require_permission("donation:read"))],
)
async def list_all_sponsorships(
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[list[SponsorshipResponse]]:
    sponsorships = await service.list_all_sponsorships()
    return ApiResponse(data=[SponsorshipResponse.model_validate(s) for s in sponsorships])


@router.get(
    "/sponsorships/{sponsorship_id}",
    response_model=ApiResponse[SponsorshipResponse],
)
async def get_sponsorship(
    sponsorship_id: uuid.UUID,
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[SponsorshipResponse]:
    sponsorship = await service.get_sponsorship(sponsorship_id)
    return ApiResponse(data=SponsorshipResponse.model_validate(sponsorship))
