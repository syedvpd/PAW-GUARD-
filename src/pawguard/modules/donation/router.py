"""API router for the Donation Management module.

Routers only validate and call services (RULE-004).
"""

import contextlib
import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
    parse_enum,
)
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.payments import PaymentGatewayError, get_payment_gateway
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
from pawguard.modules.auth.rbac import has_permission, require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.donation.models import (
    CampaignStatus,
    CampaignType,
    DonationStatus,
    DonationType,
    SponsorshipStatus,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.schemas import (
    DonationCampaignCreate,
    DonationCampaignResponse,
    DonationCampaignUpdate,
    DonationCreate,
    DonationOrderResponse,
    DonationResponse,
    DonationStatusUpdate,
    DonationVerifyRequest,
    DonorProfileCreate,
    DonorProfileResponse,
    DonorProfileUpdate,
    RecurringSubscriptionCreate,
    RecurringSubscriptionResponse,
    SponsorshipCreate,
    SponsorshipResponse,
    SponsorshipStatusUpdate,
)
from pawguard.modules.donation.service import DonationService
from pawguard.modules.finance.repository import FinanceRepository
from pawguard.modules.finance.service import FinanceService
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.storage.schemas import DownloadUrlResponse
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/donations", tags=["donations"])

# Roles allowed to see unmasked donor PII (PRR §6.1).
_UNMASKED_DONOR_PII_PERMISSIONS = {
    "donation:manage",
    "donation:read",
    "finance:read",
    "system:admin",
}


def _mask_donor_pii(
    item: DonorProfileResponse, current_user: CurrentUser
) -> DonorProfileResponse:
    """Return a copy of the response with donor PII masked unless the
    caller holds donor-management permissions or is the donor themselves."""
    is_owner = current_user.user.id == item.user_id
    user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
    if is_owner or (_UNMASKED_DONOR_PII_PERMISSIONS & user_permissions):
        return item
    masked_user = item.user
    if masked_user is not None:
        masked_user = masked_user.model_copy(
            update={
                "email": mask_email(masked_user.email),
                "full_name": mask_full_name(masked_user.full_name),
                "phone": mask_phone(masked_user.phone) if masked_user.phone else None,
            }
        )
    return item.model_copy(
        update={
            "tax_identifier": "***MASKED***" if item.tax_identifier else None,
            "user": masked_user,
        }
    )


def get_donation_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    arq_pool: Any = Depends(get_arq_pool),
) -> DonationService:
    repo = DonationRepository(db)
    dog_repo = DogRepository(db)
    notification_repo = NotificationRepository(db)
    notification_svc = NotificationService(repository=notification_repo, arq_pool=arq_pool)
    storage_svc = StorageService()
    try:
        gateway = get_payment_gateway()
    except PaymentGatewayError:
        gateway = None
    finance_svc = FinanceService(FinanceRepository(db), audit_service=audit)
    return DonationService(
        repo, dog_repo, gateway, audit_service=audit,
        notification_service=notification_svc,
        storage_service=storage_svc,
        finance_service=finance_svc,
    )


@router.post(
    "/register",
    response_model=ApiResponse[DonorProfileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register_donor(
    payload: DonorProfileCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(rate_limit("donor_register", 10, 3600))] = None,
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonorProfileResponse]:
    donor = await service.register_donor(
        current_user.id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
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
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(rate_limit("donation_checkout", 10, 60))] = None,
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationOrderResponse]:
    """Create a PENDING donation plus a payment-provider order. The client
    opens the provider's checkout with the returned order details, then calls
    `/donations/verify` once the user completes payment."""
    order = await service.initiate_online_donation(
        current_user.id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(data=order, message="Donation order created. Complete payment to confirm.")


@router.post(
    "/verify",
    response_model=ApiResponse[DonationResponse],
)
async def verify_donation_checkout(
    payload: DonationVerifyRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(rate_limit("donation_verify", 10, 60))] = None,
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationResponse]:
    donation = await service.get_donation(payload.donation_id)
    is_owner = donation.donor is not None and donation.donor.user_id == current_user.user.id
    has_staff_perm = has_permission(current_user.user, "finance:reconcile") or has_permission(current_user.user, "donation:read")
    if not is_owner and not has_staff_perm:
        raise ForbiddenError("You do not have permission to verify this donation payment.")
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
    with contextlib.suppress(ValidationFailedError, PaymentGatewayError):
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
    date_from: date | None = Query(None, description="Filter from date (ISO format)"),
    date_to: date | None = Query(None, description="Filter to date (ISO format)"),
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
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> PaginatedResponse[DonorProfileResponse]:
    result = await service.list_donors_paginated(
        page=page,
        sort=sort,
        search_term=search,
    )
    data = [_mask_donor_pii(d, current_user) for d in result.data]
    return PaginatedResponse(data=data, meta=result.meta)


@router.get(
    "/{donation_id}/receipt",
    response_model=ApiResponse[DownloadUrlResponse],
)
async def get_donation_receipt(
    donation_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> ApiResponse[DownloadUrlResponse]:
    donation = await service.get_donation(donation_id)
    is_owner = donation.donor is not None and donation.donor.user_id == current_user.user.id
    if not is_owner and not has_permission(current_user.user, "donation:read"):
        raise ForbiddenError("You do not have permission to view this receipt.")
    if donation.status.value != "success":
        raise NotFoundError("Receipt is only available for successful donations.")
    if not donation.receipt_file_key:
        from pawguard.modules.finance.repository import FinanceRepository
        from pawguard.modules.finance.service import FinanceService
        finance = FinanceService(FinanceRepository(db), audit_service=audit)
        try:
            await finance.ensure_donation_receipt(donation_id, actor_id=current_user.id)
        except Exception as exc:
            raise NotFoundError("Failed to generate receipt for this donation.") from exc
        donation = await service.get_donation(donation_id)
    if not donation.receipt_file_key:
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
    "/{donation_id}/reconcile",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("finance:create"))],
)
async def reconcile_donation(
    donation_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> ApiResponse[dict[str, Any]]:
    """Reconcile a single successful donation into the finance ledger.

    The app calls this per-donation; the bulk flow remains available at
    POST /finance/reconcile/donations. Delegates to the finance domain
    service so the reconciliation transaction/ledger rules stay in one place.
    """
    finance = FinanceService(FinanceRepository(db), audit_service=audit)
    result = await finance.reconcile_donation(
        donation_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=result,
        message="Donation reconciled successfully.",
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
    _: Annotated[None, Depends(rate_limit("sponsorship_create", 10, 3600))] = None,
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
    sponsorship = await service.get_sponsorship(sponsorship_id)
    is_owner = sponsorship.donor is not None and sponsorship.donor.user_id == current_user.user.id
    if not is_owner and not has_permission(current_user.user, "donation:manage"):
        raise ForbiddenError("You do not have permission to update this sponsorship.")
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
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[SponsorshipResponse]:
    sponsorship = await service.get_sponsorship(sponsorship_id)
    is_owner = sponsorship.donor is not None and sponsorship.donor.user_id == current_user.user.id
    if not is_owner and not has_permission(current_user.user, "donation:read"):
        raise ForbiddenError("You do not have permission to view this sponsorship.")
    return ApiResponse(data=SponsorshipResponse.model_validate(sponsorship))


# ── Donation campaigns (PRR 3.1.7 / 3.11) ─────────────────────────────────


@router.get(
    "/campaigns",
    response_model=ApiResponse[list[DonationCampaignResponse]],
)
async def list_public_campaigns(
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[list[DonationCampaignResponse]]:
    """Public listing of currently accepting donation campaigns."""
    campaigns = await service.list_active_campaigns()
    return ApiResponse(
        data=[await service._to_campaign_response(c) for c in campaigns],
    )


@router.get(
    "/campaigns/manage",
    response_model=PaginatedResponse[DonationCampaignResponse],
    dependencies=[Depends(require_permission("donation:read"))],
)
async def list_all_campaigns(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search campaigns by name/description"),
    status: CampaignStatus | None = Query(None, description="Filter by status"),
    campaign_type: CampaignType | None = Query(None, description="Filter by type"),
    service: DonationService = Depends(get_donation_service),
) -> PaginatedResponse[DonationCampaignResponse]:
    return await service.list_campaigns_paginated(
        page=page,
        sort=sort,
        search_term=search,
        status=status,
        campaign_type=campaign_type.value if campaign_type else None,
    )


@router.post(
    "/campaigns",
    response_model=ApiResponse[DonationCampaignResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("donation:manage"))],
)
async def create_campaign(
    payload: DonationCampaignCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationCampaignResponse]:
    campaign = await service.create_campaign(
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=await service._to_campaign_response(campaign),
        message="Donation campaign created successfully.",
    )


@router.get(
    "/campaigns/{campaign_id}",
    response_model=ApiResponse[DonationCampaignResponse],
)
async def get_campaign(
    campaign_id: uuid.UUID,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationCampaignResponse]:
    campaign = await service.get_campaign(campaign_id)
    return ApiResponse(data=await service._to_campaign_response(campaign))


@router.patch(
    "/campaigns/{campaign_id}",
    response_model=ApiResponse[DonationCampaignResponse],
    dependencies=[Depends(require_permission("donation:update"))],
)
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: DonationCampaignUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationCampaignResponse]:
    campaign = await service.update_campaign(
        campaign_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=await service._to_campaign_response(campaign),
        message="Donation campaign updated successfully.",
    )


@router.delete(
    "/campaigns/{campaign_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("donation:update"))],
)
async def delete_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[None]:
    await service.soft_delete_campaign(
        campaign_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(message="Donation campaign deleted successfully.")


# ── Donor self-service ──────────────────────────────────────────────


@router.get(
    "/donors/me",
    response_model=ApiResponse[DonorProfileResponse],
)
async def get_my_donor_profile(
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonorProfileResponse]:
    donor = await service.get_or_create_donor(current_user.id)
    return ApiResponse(
        data=DonorProfileResponse.model_validate(donor),
        message="Donor profile retrieved.",
    )


# ── Recurring subscriptions (audit 3.11) ────────────────────────────


@router.post(
    "/recurring",
    response_model=ApiResponse[RecurringSubscriptionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_recurring_subscription(
    payload: RecurringSubscriptionCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[RecurringSubscriptionResponse]:
    subscription = await service.create_recurring_subscription(
        current_user.id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RecurringSubscriptionResponse.model_validate(subscription),
        message="Recurring subscription created successfully.",
    )


@router.get(
    "/recurring",
    response_model=ApiResponse[list[RecurringSubscriptionResponse]],
)
async def list_my_recurring_subscriptions(
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[list[RecurringSubscriptionResponse]]:
    donor = await service._repo.get_donor_by_user_id(current_user.id)
    if donor is None:
        return ApiResponse(data=[], message="No recurring subscriptions found.")
    subscriptions = await service._repo.get_recurring_subscriptions_for_donor(
        donor.id,
    )
    return ApiResponse(
        data=[
            RecurringSubscriptionResponse.model_validate(s)
            for s in subscriptions
        ],
        message="Recurring subscriptions retrieved.",
    )


@router.delete(
    "/recurring/{subscription_id}",
    response_model=ApiResponse[RecurringSubscriptionResponse],
)
async def cancel_recurring_subscription(
    subscription_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[RecurringSubscriptionResponse]:
    subscription = await service._repo.get_recurring_subscription_by_id(
        subscription_id,
    )
    if subscription is None:
        raise NotFoundError("Recurring subscription not found.")
    is_owner = (
        subscription.donor is not None
        and subscription.donor.user_id == current_user.user.id
    )
    if not is_owner and not has_permission(
        current_user.user, "donation:manage"
    ):
        raise ForbiddenError(
            "You do not have permission to cancel this subscription."
        )
    updated = await service.cancel_recurring_subscription(
        subscription_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=RecurringSubscriptionResponse.model_validate(updated),
        message="Recurring subscription cancelled successfully.",
    )
