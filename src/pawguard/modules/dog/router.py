"""API router for the Dog Management module. Routers only validate and call services (RULE-004)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.cache_decorator import cache_response
from pawguard.core.exceptions import NotFoundError, parse_enum
from pawguard.core.logging import get_logger
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.rate_limiter import rate_limit, resolve_client_ip
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import (
    CurrentUser,
    get_current_user,
    get_optional_current_user,
)
from pawguard.modules.auth.permission_codes import FOSTER_APPROVE, SHELTER_READ
from pawguard.modules.auth.rbac import has_permission, is_admin_role, require_permission
from pawguard.modules.companion_pet.router import get_companion_pet_service
from pawguard.modules.companion_pet.service import CompanionPetService
from pawguard.modules.dog.models import (
    DogBreedClassification,
    DogGender,
    DogStatus,
    DogTemperament,
)
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.schemas import (
    DogActivityLogResponse,
    DogProfileCreate,
    DogProfileResponse,
    DogProfileUpdate,
    DogSafetyTagProvisionResponse,
    DogSafetyTagResolveRequest,
    DogSafetyTagResolveResponse,
    DogSafetyTagResponse,
    DogStatusUpdate,
    DogWeightLogCreate,
    DogWeightLogResponse,
    PublicDogScanResponse,
)
from pawguard.modules.dog.service import DogService
from pawguard.redis.client import RedisClient, get_redis
from pawguard.services.audit_service import AuditService

logger = get_logger(__name__)

router = APIRouter(prefix="/dogs", tags=["dogs"])


def get_dog_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    redis: RedisClient = Depends(get_redis),
) -> DogService:
    return DogService(DogRepository(db), audit_service=audit, redis=redis)


def _public_dog_view(dog: DogProfileResponse) -> DogProfileResponse:
    """Public adoption-directory view: strips internal identifiers (rescue
    case link, microchip, facility/section/kennel/foster-home UUIDs) that are
    meaningless - and potentially sensitive - on the anonymous public catalog."""
    return dog.model_copy(
        update={
            "microchip_id": None,
            "rescue_case_id": None,
            "shelter_facility_id": None,
            "section_id": None,
            "kennel_id": None,
            "foster_home_id": None,
        }
    )


def _public_view_enabled(current_user: CurrentUser | None) -> bool:
    """Public endpoint - always return true for public access.
    The adoption directory only shows adoptable dogs with public view."""
    return True


@router.post(
    "",
    response_model=ApiResponse[DogProfileResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def register_dog(
    payload: DogProfileCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.register_dog(
        payload,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog profile registered successfully.",
    )


@router.get(
    "",
    response_model=PaginatedResponse[DogProfileResponse],
)
@cache_response(ttl_seconds=120, namespace="dog")
async def list_dogs(
    request: Request,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by name, breed, registration number"),
    status: DogStatus | None = Query(None, description="Filter by status"),
    is_adoptable: bool | None = Query(None, description="Filter by adoptable status"),
    breed: str | None = Query(None, description="Filter by breed"),
    breed_classification: DogBreedClassification | None = Query(
        None, description="Filter by Pure/Mix/Unknown classification"
    ),
    gender: DogGender | None = Query(None, description="Filter by sex"),
    temperament: DogTemperament | None = Query(None, description="Filter by temperament"),
    min_age_months: int | None = Query(None, ge=0, description="Minimum age in months"),
    max_age_months: int | None = Query(None, ge=0, description="Maximum age in months"),
    min_weight: float | None = Query(None, ge=0.0, description="Minimum weight in kg"),
    max_weight: float | None = Query(None, ge=0.0, description="Maximum weight in kg"),
    location: str | None = Query(
        None,
        description=(
            "Free-text match on the shelter facility name/address; only dogs "
            "assigned to a facility are returned when this filter is active"
        ),
    ),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: DogService = Depends(get_dog_service),
) -> PaginatedResponse[DogProfileResponse]:
    # Public adoption directory: only shelter staff (``shelter:read``), foster
    # coordinators (``foster:approve`` - they place non-adoptable dogs into
    # foster care, so they need the full catalogue too), and admins may browse
    # the full dog catalogue. Every other caller - anonymous visitors AND
    # authenticated adopters/app users - sees only adoptable dogs so
    # already-adopted animals never leak into the public adoption page.
    is_staff = current_user is not None and (
        has_permission(current_user.user, SHELTER_READ)
        or has_permission(current_user.user, FOSTER_APPROVE)
        or is_admin_role(current_user.claims)
    )
    public_view = not is_staff
    if public_view:
        is_adoptable = True
    result = await service.list_dogs_paginated(
        page=page,
        sort=sort,
        search_term=search,
        status=status,
        is_adoptable=is_adoptable,
        breed=breed,
        breed_classification=breed_classification,
        gender=gender,
        temperament=temperament,
        min_age_months=min_age_months,
        max_age_months=max_age_months,
        min_weight=min_weight,
        max_weight=max_weight,
        location=location,
    )
    data = [DogProfileResponse.model_validate(d) for d in result.data]
    if public_view:
        data = [_public_dog_view(d) for d in data]
    return PaginatedResponse(data=data, meta=result.meta)


@router.get(
    "/admin/dogs/{dog_id}",
    response_model=ApiResponse[DogProfileResponse],
)
@router.get(
    "/{dog_id}",
    response_model=ApiResponse[DogProfileResponse],
)
async def get_dog(
    dog_id: str,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.get_dog(dog_id)

    # Check caller permissions - shelter staff/admin may view any dog profile,
    # everyone else (including authenticated adopters) may only view public
    # details for adoptable dogs.
    is_staff = current_user is not None and (
        has_permission(current_user.user, SHELTER_READ)
        or has_permission(current_user.user, FOSTER_APPROVE)
        or is_admin_role(current_user.claims)
    )

    if not is_staff and not dog.is_adoptable:
        raise NotFoundError(
            "Dog profile is currently in intake/treatment and not yet available for public adoption."
        )
    if not is_staff and dog.status == DogStatus.ADOPTED:
        raise NotFoundError("This dog has already been adopted and is no longer available.")

    data = DogProfileResponse.model_validate(dog)
    if not is_staff:
        data = _public_dog_view(data)
    return ApiResponse(data=data)


@router.get(
    "/{dog_id}/timeline",
    response_model=ApiResponse[list[DogActivityLogResponse]],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def get_dog_timeline(
    dog_id: uuid.UUID,
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[list[DogActivityLogResponse]]:
    """Lifecycle activity stream for a dog's master profile (PRR 3.4)."""
    logs = await service.get_dog_timeline(dog_id)
    return ApiResponse(
        data=[DogActivityLogResponse.model_validate(log) for log in logs],
        message=f"{len(logs)} activity event(s).",
    )


@router.get(
    "/{dog_id}/public-scan",
    response_model=ApiResponse[PublicDogScanResponse],
    dependencies=[Depends(rate_limit("dog_public_scan", max_requests=20, window_seconds=60))],
    summary="Privacy-safe public dog QR scan",
)
async def public_scan_dog(
    dog_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: DogService = Depends(get_dog_service),
    companion_service: CompanionPetService = Depends(get_companion_pet_service),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PublicDogScanResponse]:
    """Return live public-safe status for any non-deleted dog, regardless of status."""
    resolve_client_ip(request)
    try:
        dog = await service.get_dog(dog_id)
    except NotFoundError:
        dog = None

    if dog is not None:
        public = _public_dog_view(DogProfileResponse.model_validate(dog))
        photo_urls = await service.get_dog_photo_urls(dog_id)

        adopter_name: str | None = None
        adopter_phone: str | None = None
        adopter_email: str | None = None
        adopter_name, adopter_phone, adopter_email = await service.get_adopter_contact(dog_id)

        return ApiResponse(
            data=PublicDogScanResponse(
                name=public.name,
                breed=public.breed,
                breed_classification=public.breed_classification,
                estimated_age=public.estimated_age,
                gender=public.gender,
                weight_kg=public.weight,
                temperament=public.temperament,
                color=public.color,
                photo_gallery_urls=photo_urls,
                current_status=public.status,
                is_adoptable=public.is_adoptable,
                registration_number=public.registration_number,
                adopter_name=adopter_name,
                adopter_phone=adopter_phone,
                adopter_email=adopter_email,
            )
        )

    # Fallback: check if dog_id is a CompanionPet ID
    try:
        _tag, pet, lost_info = await companion_service.public_scan_companion_pet(
            dog_id, resolve_client_ip(request)
        )
        photo_url = await companion_service.get_pet_photo_url(pet.id)
        return ApiResponse(
            data=PublicDogScanResponse(
                name=pet.name,
                breed=pet.breed or "Mixed",
                breed_classification=DogBreedClassification.MIX,
                estimated_age=None,
                gender=(
                    DogGender.MALE
                    if (pet.sex and pet.sex.lower() in ("male", "m"))
                    else (
                        DogGender.FEMALE
                        if (pet.sex and pet.sex.lower() in ("female", "f"))
                        else DogGender.UNKNOWN
                    )
                ),
                weight_kg=None,
                temperament=None,
                color=pet.color,
                photo_gallery_urls=[photo_url] if photo_url else [],
                current_status=DogStatus.ADOPTED,
                is_adoptable=False,
                registration_number=f"PET-{str(pet.id)[:8]}",
                adopter_name=lost_info.get("owner_name"),
                adopter_phone=lost_info.get("owner_phone"),
                adopter_email=None,
            )
        )
    except Exception:
        raise NotFoundError(f"Dog {dog_id} not found") from None


@router.get(
    "/{dog_id}/qr-image",
    response_class=Response,
    dependencies=[Depends(require_permission("shelter:update"))],
    summary="Generate a staff-only dog profile QR image",
)
async def dog_qr_image(
    dog_id: uuid.UUID,
    service: DogService = Depends(get_dog_service),
) -> Response:
    dog = await service.get_dog(dog_id)
    return Response(
        content=service.qr_image(dog),
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{dog.registration_number}.png"'},
    )


@router.post(
    "/{dog_id}/weight",
    response_model=ApiResponse[DogWeightLogResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def record_dog_weight(
    dog_id: uuid.UUID,
    payload: DogWeightLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogWeightLogResponse]:
    """Append a weight measurement to a dog's history (PRR 3.4)."""
    log = await service.record_weight(
        dog_id,
        payload,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=DogWeightLogResponse.model_validate(log),
        message="Weight recorded successfully.",
    )


@router.get(
    "/{dog_id}/weights",
    response_model=ApiResponse[list[DogWeightLogResponse]],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def get_dog_weight_history(
    dog_id: uuid.UUID,
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[list[DogWeightLogResponse]]:
    """Chronological weight history for a dog (PRR 3.4)."""
    logs = await service.get_weight_history(dog_id)
    return ApiResponse(
        data=[DogWeightLogResponse.model_validate(log) for log in logs],
        message=f"{len(logs)} weight record(s).",
    )


@router.put(
    "/{dog_id}",
    response_model=ApiResponse[DogProfileResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_dog(
    dog_id: uuid.UUID,
    payload: DogProfileUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.update_dog(
        dog_id,
        payload,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog profile updated successfully.",
    )


@router.patch(
    "/{dog_id}/status",
    response_model=ApiResponse[DogProfileResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
@router.patch(
    "/admin/dogs/{dog_id}/status",
    response_model=ApiResponse[DogProfileResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_dog_status(
    dog_id: uuid.UUID,
    payload: DogStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.update_dog_status(
        dog_id,
        payload.status,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog status updated successfully.",
    )


@router.delete(
    "/{dog_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def soft_delete_dog(
    dog_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[None]:
    await service.soft_delete_dog(
        dog_id,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(message="Dog profile deleted successfully.")


@router.post(
    "/bulk/status-update",
    response_model=ApiResponse[BulkStatusUpdateResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_update_dog_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[BulkStatusUpdateResponse]:
    updated = await service.bulk_update_status(
        payload.ids,
        parse_enum(DogStatus, payload.status),
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=BulkStatusUpdateResponse(
            message=f"{updated} dog(s) status updated.",
            updated_count=updated,
        ),
    )


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_delete_dogs(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[BulkDeleteResponse]:
    deleted = await service.bulk_soft_delete(payload.ids, current_user.id)
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} dog(s) deleted.",
            deleted_count=deleted,
        ),
    )


@router.post(
    "/{dog_id}/safety-tag",
    response_model=ApiResponse[DogSafetyTagProvisionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("safety_tag:manage"))],
    summary="Provision a permanent Safety Tag for a Dog Master profile",
)
async def provision_dog_safety_tag(
    dog_id: uuid.UUID,
    request: Request,
    force_reissue: bool = Query(
        False,
        description="If true, revokes existing active tag and provisions a replacement token.",
    ),
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[DogSafetyTagProvisionResponse]:
    tag, raw_token = await service.provision_dog_safety_tag(
        dog_id, current_user, force_reissue=force_reissue, ip_address=resolve_client_ip(request)
    )
    data = DogSafetyTagProvisionResponse(
        id=tag.id,
        dog_id=tag.dog_id,
        pet_id=tag.pet_id,
        token_prefix=tag.token_prefix,
        is_active=tag.is_active,
        last_scanned_at=tag.last_scanned_at,
        scan_count=tag.scan_count,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
        raw_token=raw_token,
    )
    return ApiResponse(data=data, message="Safety Tag provisioned successfully.")


@router.get(
    "/{dog_id}/safety-tag",
    response_model=ApiResponse[DogSafetyTagResponse],
    dependencies=[Depends(require_permission("safety_tag:manage"))],
    summary="Get active Safety Tag metadata for a Dog Master profile",
)
async def get_dog_safety_tag(
    dog_id: uuid.UUID,
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[DogSafetyTagResponse]:
    tag = await service.get_dog_safety_tag(dog_id)
    if tag is None:
        raise NotFoundError("Safety Tag not found for this dog.")
    data = DogSafetyTagResponse.model_validate(tag)
    return ApiResponse(data=data)


@router.delete(
    "/{dog_id}/safety-tag",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("safety_tag:manage"))],
    summary="Deactivate/revoke active Safety Tag for tag replacement",
)
async def deactivate_dog_safety_tag(
    dog_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[None]:
    await service.deactivate_dog_safety_tag(
        dog_id, current_user, ip_address=resolve_client_ip(request)
    )
    return ApiResponse(message="Safety Tag deactivated successfully.")


@router.post(
    "/safety-tag/resolve",
    response_model=ApiResponse[DogSafetyTagResolveResponse],
    dependencies=[Depends(require_permission("dog:read"))],
    summary="Resolve a Safety Tag raw_token to its exact Dog Master profile",
)
async def resolve_dog_safety_tag(
    payload: DogSafetyTagResolveRequest,
    request: Request,
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[DogSafetyTagResolveResponse]:
    tag, pet, lost_info = await service.scan_safety_tag(
        payload.raw_token, resolve_client_ip(request)
    )
    if tag is None:
        raise NotFoundError("Safety Tag not found.")

    dog = getattr(tag, "dog", None)
    if dog is None and tag.dog_id:
        dog_repo = DogRepository(service._session)
        dog = await dog_repo.get_by_id(tag.dog_id)

    if dog is None:
        raise NotFoundError("Dog Master profile not found for this Safety Tag.")

    data = DogSafetyTagResolveResponse(
        tag_id=tag.id,
        dog_id=dog.id,
        token_prefix=tag.token_prefix,
        is_active=tag.is_active,
        last_scanned_at=tag.last_scanned_at,
        scan_count=tag.scan_count,
        dog=DogProfileResponse.model_validate(dog),
    )
    return ApiResponse(data=data)
