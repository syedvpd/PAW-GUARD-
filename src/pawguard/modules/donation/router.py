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
from pawguard.core.exceptions import ValidationFailedError
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.payments import PaymentGatewayError, get_payment_gateway
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.donation.models import DonationStatus, DonationType
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
)
from pawguard.modules.donation.service import DonationService

router = APIRouter(prefix="/donations", tags=["donations"])


def get_donation_service(db: AsyncSession = Depends(get_db)) -> DonationService:
    repo = DonationRepository(db)
    dog_repo = DogRepository(db)
    try:
        gateway = get_payment_gateway()
    except PaymentGatewayError:
        gateway = None
    return DonationService(repo, dog_repo, gateway)


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
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonorProfileResponse]:
    donor = await service.update_donor(donor_id, payload)
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
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[None]:
    await service.soft_delete_donor(donor_id)
    return ApiResponse(message="Donor profile deleted successfully.")


@router.post(
    "",
    response_model=ApiResponse[DonationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def make_donation(
    payload: DonationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationResponse]:
    donation = await service.make_donation(current_user.id, payload)
    return ApiResponse(
        data=DonationResponse.model_validate(donation),
        message="Thank you! Donation processed successfully.",
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
    current_user: CurrentUser = Depends(get_current_user),
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationResponse]:
    donation = await service.verify_donation_payment(
        donation_id=payload.donation_id,
        gateway_order_id=payload.gateway_order_id,
        gateway_payment_id=payload.gateway_payment_id,
        gateway_signature=payload.gateway_signature,
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


@router.patch(
    "/{donation_id}/status",
    response_model=ApiResponse[DonationResponse],
    dependencies=[Depends(require_permission("donation:update"))],
)
async def update_donation_status(
    donation_id: uuid.UUID,
    payload: DonationStatusUpdate,
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[DonationResponse]:
    donation = await service.update_donation_status(donation_id, payload.status)
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
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[BulkStatusUpdateResponse]:
    updated = await service.bulk_update_status(
        payload.ids,
        DonationStatus(payload.status),
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
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[BulkDeleteResponse]:
    deleted = await service.bulk_soft_delete(payload.ids)
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} donor(s) deleted.",
            deleted_count=deleted,
        ),
    )
