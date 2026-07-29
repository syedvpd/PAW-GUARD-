"""API router for the Dog Management module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.schemas import DogProfileCreate, DogProfileResponse, DogProfileUpdate
from pawguard.modules.dog.service import DogService

router = APIRouter(prefix="/dogs", tags=["dogs"])


def get_dog_service(db: AsyncSession = Depends(get_db)) -> DogService:
    repo = DogRepository(db)
    return DogService(repo)


@router.post(
    "",
    response_model=ApiResponse[DogProfileResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def register_dog(
    payload: DogProfileCreate,
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.register_dog(payload)
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog profile registered successfully.",
    )


@router.put(
    "/{dog_id}",
    response_model=ApiResponse[DogProfileResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_dog(
    dog_id: uuid.UUID,
    payload: DogProfileUpdate,
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.update_dog(dog_id, payload)
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog profile updated successfully.",
    )


@router.get(
    "/{dog_id}",
    response_model=ApiResponse[DogProfileResponse],
    dependencies=[Depends(require_permission("public:read"))],
)
async def get_dog(
    dog_id: uuid.UUID,
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.get_dog(dog_id)
    return ApiResponse(data=DogProfileResponse.model_validate(dog))


@router.get(
    "",
    response_model=ApiResponse[list[DogProfileResponse]],
    dependencies=[Depends(require_permission("public:read"))],
)
async def list_dogs(
    status: DogStatus | None = None,
    is_adoptable: bool | None = None,
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[list[DogProfileResponse]]:
    dogs = await service.list_dogs(status=status, is_adoptable=is_adoptable)
    return ApiResponse(data=[DogProfileResponse.model_validate(d) for d in dogs])
