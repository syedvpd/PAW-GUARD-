"""API router for the Donation Management module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import get_current_user, CurrentUser
from pawguard.modules.auth.models import User
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.schemas import (
    DonationCreate,
    DonationResponse,
    DonorProfileCreate,
    DonorProfileResponse,
)
from pawguard.modules.donation.service import DonationService

router = APIRouter(prefix="/donations", tags=["donations"])


def get_donation_service(db: AsyncSession = Depends(get_db)) -> DonationService:
    repo = DonationRepository(db)
    dog_repo = DogRepository(db)
    return DonationService(repo, dog_repo)


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
    response_model=ApiResponse[list[DonationResponse]],
    dependencies=[Depends(require_permission("donation:read"))],
)
async def list_all_donations(
    service: DonationService = Depends(get_donation_service),
) -> ApiResponse[list[DonationResponse]]:
    donations = await service.list_all_donations()
    return ApiResponse(data=[DonationResponse.model_validate(d) for d in donations])
