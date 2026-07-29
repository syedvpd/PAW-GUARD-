"""API router for the Adoption Management module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import ForbiddenError
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.adoption.models import AdoptionStatus
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import (
    AdoptionApplicationCreate,
    AdoptionApplicationResponse,
    AdoptionApplicationUpdate,
)
from pawguard.modules.adoption.service import AdoptionService
from pawguard.modules.auth.dependencies import get_current_user, CurrentUser
from pawguard.modules.auth.models import User
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository

router = APIRouter(prefix="/adoptions", tags=["adoptions"])


def get_adoption_service(db: AsyncSession = Depends(get_db)) -> AdoptionService:
    repo = AdoptionRepository(db)
    dog_repo = DogRepository(db)
    return AdoptionService(repo, dog_repo)


@router.post(
    "",
    response_model=ApiResponse[AdoptionApplicationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def apply_for_adoption(
    payload: AdoptionApplicationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionApplicationResponse]:
    app = await service.apply_for_adoption(current_user.user.id, payload)
    return ApiResponse(
        data=AdoptionApplicationResponse.model_validate(app),
        message="Adoption application submitted successfully.",
    )


@router.put(
    "/{app_id}",
    response_model=ApiResponse[AdoptionApplicationResponse],
    dependencies=[Depends(require_permission("adoption:process"))],
)
async def update_application(
    app_id: uuid.UUID,
    payload: AdoptionApplicationUpdate,
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionApplicationResponse]:
    app = await service.update_application(app_id, payload)
    return ApiResponse(
        data=AdoptionApplicationResponse.model_validate(app),
        message="Adoption application updated successfully.",
    )


@router.get(
    "/{app_id}",
    response_model=ApiResponse[AdoptionApplicationResponse],
)
async def get_application(
    app_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[AdoptionApplicationResponse]:
    app = await service.get_application(app_id)

    # Allow reading if the user is the adopter or holds the internal adoption:read permission
    user_permissions = {p.code for r in current_user.user.roles for p in r.permissions}
    if app.adopter_id != current_user.user.id and "adoption:read" not in user_permissions:
        raise ForbiddenError("You do not have permission to view this application.")

    return ApiResponse(data=AdoptionApplicationResponse.model_validate(app))


@router.get(
    "",
    response_model=ApiResponse[list[AdoptionApplicationResponse]],
    dependencies=[Depends(require_permission("adoption:read"))],
)
async def list_applications(
    dog_id: uuid.UUID | None = None,
    adopter_id: uuid.UUID | None = None,
    status: AdoptionStatus | None = None,
    service: AdoptionService = Depends(get_adoption_service),
) -> ApiResponse[list[AdoptionApplicationResponse]]:
    apps = await service.list_applications(dog_id=dog_id, adopter_id=adopter_id, status=status)
    return ApiResponse(data=[AdoptionApplicationResponse.model_validate(a) for a in apps])
