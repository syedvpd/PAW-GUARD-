"""Shelter & Capacity API router.

Routers only validate and call services (RULE-004).
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.cache_decorator import cache_response
from pawguard.core.exceptions import parse_enum
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.service import InventoryService
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.shelter.models import (
    FacilityStatus,
    FacilityType,
    KennelSanitationState,
    SectionType,
    ShelterVetRequestStatus,
)
from pawguard.modules.shelter.repository import ShelterRepository
from pawguard.modules.shelter.schemas import (
    DailyCareLogCreate,
    DailyCareLogResponse,
    FacilityStatusUpdate,
    FacilityTransferCancel,
    FacilityTransferCreate,
    FacilityTransferResponse,
    KennelAssignmentRequest,
    KennelCleaningLogCreate,
    KennelCleaningLogResponse,
    KennelCreate,
    KennelResponse,
    ShelterFacilityCreate,
    ShelterFacilityResponse,
    ShelterFacilityUpdate,
    ShelterSectionCreate,
    ShelterSectionResponse,
    ShelterVetCheckRequest,
    ShelterVetCheckResponse,
    ShelterVetRequestListResponse,
    SuggestedQuarantineKennelResponse,
)
from pawguard.modules.shelter.service import ShelterService
from pawguard.services.audit_service import AuditService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/shelter", tags=["shelter"])


def get_shelter_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    arq_pool: Any = Depends(get_arq_pool),
) -> ShelterService:
    repo = ShelterRepository(db)
    dog_repo = DogRepository(db)
    notification_svc = NotificationService(repository=NotificationRepository(db), arq_pool=arq_pool)
    inventory = InventoryService(
        InventoryRepository(db), audit_service=audit, notification_service=notification_svc
    )
    return ShelterService(
        repo,
        dog_repo,
        audit_service=audit,
        inventory_service=inventory,
        notification_service=notification_svc,
    )


@router.post(
    "/facilities",
    response_model=ApiResponse[ShelterFacilityResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_facility(
    payload: ShelterFacilityCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.create_facility(
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ShelterFacilityResponse.model_validate(facility),
        message="Shelter facility created successfully.",
    )


@router.get(
    "/facilities",
    response_model=PaginatedResponse[ShelterFacilityResponse],
    dependencies=[Depends(require_permission("shelter:read"))],
)
@cache_response(ttl_seconds=60, namespace="shelter")
async def list_facilities(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    status: FacilityStatus | None = None,
    facility_type: FacilityType | None = None,
    service: ShelterService = Depends(get_shelter_service),
) -> PaginatedResponse[ShelterFacilityResponse]:
    result = await service.list_facilities_paginated(
        page,
        sort,
        search_term=search,
        status=status,
        facility_type=facility_type,
    )
    return PaginatedResponse(
        data=[ShelterFacilityResponse.model_validate(f) for f in result.data],
        meta=result.meta,
    )


@router.get(
    "/facilities/{facility_id}",
    response_model=ApiResponse[ShelterFacilityResponse],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def get_facility(
    facility_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.get_facility(facility_id)
    return ApiResponse(
        data=ShelterFacilityResponse.model_validate(facility),
    )


@router.put(
    "/facilities/{facility_id}",
    response_model=ApiResponse[ShelterFacilityResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_facility(
    facility_id: uuid.UUID,
    payload: ShelterFacilityUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.update_facility(
        facility_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ShelterFacilityResponse.model_validate(facility),
        message="Shelter facility updated successfully.",
    )


@router.post(
    "/facilities/{facility_id}/sections",
    response_model=ApiResponse[ShelterSectionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_section(
    facility_id: uuid.UUID,
    payload: ShelterSectionCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterSectionResponse]:
    section = await service.create_section(
        facility_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ShelterSectionResponse.model_validate(section),
        message="Shelter section created successfully.",
    )


@router.get(
    "/facilities/{facility_id}/sections",
    response_model=PaginatedResponse[ShelterSectionResponse],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def list_sections(
    facility_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    section_type: SectionType | None = None,
    service: ShelterService = Depends(get_shelter_service),
) -> PaginatedResponse[ShelterSectionResponse]:
    result = await service.list_sections_paginated(
        page,
        sort,
        facility_id=facility_id,
        section_type=section_type,
        search_term=search,
    )
    return PaginatedResponse(
        data=[ShelterSectionResponse.model_validate(s) for s in result.data],
        meta=result.meta,
    )


@router.post(
    "/sections/{section_id}/kennels",
    response_model=ApiResponse[KennelResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def create_kennel(
    section_id: uuid.UUID,
    payload: KennelCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[KennelResponse]:
    kennel = await service.create_kennel(
        section_id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=KennelResponse.model_validate(kennel),
        message="Kennel created successfully.",
    )


@router.get(
    "/sections/{section_id}/kennels",
    response_model=PaginatedResponse[KennelResponse],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def list_kennels(
    section_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    service: ShelterService = Depends(get_shelter_service),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[KennelResponse]:
    result = await service.list_kennels_paginated(
        page,
        sort,
        section_id=section_id,
    )
    # Enrich with occupancy + transfer-reservation data
    from sqlalchemy import select

    from pawguard.modules.dog.models import DogProfile
    from pawguard.modules.shelter.models import FacilityTransfer, TransferStatus

    kennel_ids = [k.id for k in result.data]
    if kennel_ids:
        occ_stmt = select(DogProfile.kennel_id, DogProfile.id).where(
            DogProfile.kennel_id.in_(kennel_ids),
            DogProfile.deleted_at.is_(None),
        )
        rows = (await db.execute(occ_stmt)).all()
        occ_map: dict[uuid.UUID, uuid.UUID] = {row[0]: row[1] for row in rows}

        reserved_stmt = select(FacilityTransfer.destination_kennel_id).where(
            FacilityTransfer.destination_kennel_id.in_(kennel_ids),
            FacilityTransfer.status.in_([TransferStatus.PENDING, TransferStatus.IN_TRANSIT]),
        )
        reserved_ids = {row[0] for row in (await db.execute(reserved_stmt)).all()}
    else:
        occ_map = {}
        reserved_ids = set()

    enriched = []
    for k in result.data:
        dog_id = occ_map.get(k.id)
        enriched.append(
            KennelResponse(
                id=k.id,
                section_id=k.section_id,
                identifier=k.identifier,
                capacity=k.capacity,
                sanitation_state=k.sanitation_state,
                is_occupied=dog_id is not None,
                occupied_by_dog_id=dog_id,
                is_reserved_for_transfer=k.id in reserved_ids,
                created_at=k.created_at,
                updated_at=k.updated_at,
            )
        )

    return PaginatedResponse(data=enriched, meta=result.meta)


@router.get(
    "/kennels/suggest-quarantine",
    response_model=ApiResponse[SuggestedQuarantineKennelResponse | None],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def suggest_quarantine_kennel(
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[SuggestedQuarantineKennelResponse | None]:
    """A suggestion only, for the intake screen to pre-fill — staff still
    confirm placement via the normal assign endpoint (PRR: no silent
    auto-commit on ADMITTED)."""
    result = await service.suggest_quarantine_kennel()
    if result is None:
        return ApiResponse(data=None)
    kennel, section = result
    return ApiResponse(
        data=SuggestedQuarantineKennelResponse(
            kennel_id=kennel.id,
            kennel_identifier=kennel.identifier,
            section_id=section.id,
            facility_id=section.facility_id,
        )
    )


@router.post(
    "/kennels/{kennel_id}/assign/{dog_id}",
    response_model=ApiResponse[bool],
    dependencies=[Depends(require_permission("shelter:update"))],
)
@router.patch(
    "/kennels/{kennel_id}/assign/{dog_id}",
    response_model=ApiResponse[bool],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def assign_dog_to_kennel(
    kennel_id: uuid.UUID,
    dog_id: uuid.UUID,
    request: Request,
    payload: KennelAssignmentRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[bool]:
    body = payload or KennelAssignmentRequest()
    success = await service.assign_dog_to_kennel(
        dog_id,
        kennel_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        emergency_override=body.emergency_override,
        override_notes=body.override_notes,
    )
    return ApiResponse(
        data=success,
        message="Dog successfully assigned to kennel.",
    )


@router.put(
    "/kennels/{kennel_id}/sanitation",
    response_model=ApiResponse[KennelResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_kennel_sanitation(
    kennel_id: uuid.UUID,
    status_val: KennelSanitationState,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[KennelResponse]:
    kennel = await service.update_kennel_sanitation(
        kennel_id,
        status_val,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=KennelResponse.model_validate(kennel),
        message="Kennel sanitation status updated successfully.",
    )


@router.post(
    "/kennels/{kennel_id}/cleaning-logs",
    response_model=ApiResponse[KennelCleaningLogResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def log_kennel_cleaning(
    kennel_id: uuid.UUID,
    payload: KennelCleaningLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[KennelCleaningLogResponse]:
    log = await service.log_kennel_cleaning(
        kennel_id,
        cleaned_by_id=current_user.id,
        payload=payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=KennelCleaningLogResponse.model_validate(log),
        message="Kennel cleaning rotation logged successfully.",
    )


@router.get(
    "/kennels/{kennel_id}/cleaning-logs",
    response_model=PaginatedResponse[KennelCleaningLogResponse],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def list_kennel_cleaning_logs(
    kennel_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    service: ShelterService = Depends(get_shelter_service),
) -> PaginatedResponse[KennelCleaningLogResponse]:
    result = await service.list_cleaning_logs_paginated(
        page,
        sort,
        kennel_id=kennel_id,
    )
    return PaginatedResponse(
        data=[KennelCleaningLogResponse.model_validate(log) for log in result.data],
        meta=result.meta,
    )


@router.post(
    "/transfers",
    response_model=ApiResponse[FacilityTransferResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def request_transfer(
    payload: FacilityTransferCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[FacilityTransferResponse]:
    transfer = await service.request_transfer(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=FacilityTransferResponse.model_validate(transfer),
        message=("Inter-facility transfer request submitted successfully."),
    )


@router.get(
    "/transfers",
    response_model=ApiResponse[list[FacilityTransferResponse]],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def list_transfers(
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[list[FacilityTransferResponse]]:
    transfers = await service.list_transfers()
    return ApiResponse(
        data=[FacilityTransferResponse.model_validate(t) for t in transfers],
    )


@router.get(
    "/transfers/{transfer_id}",
    response_model=ApiResponse[FacilityTransferResponse],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def get_transfer(
    transfer_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[FacilityTransferResponse]:
    transfer = await service.get_transfer(transfer_id)
    return ApiResponse(
        data=FacilityTransferResponse.model_validate(transfer),
    )


@router.post(
    "/transfers/{transfer_id}/confirm-sender",
    response_model=ApiResponse[FacilityTransferResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def confirm_transfer_sender(
    transfer_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[FacilityTransferResponse]:
    """Confirmation from the SENDING facility. A transfer only completes
    once both this and /confirm-receiver have been called (PRR 3.6)."""
    transfer = await service.confirm_transfer_sender(
        transfer_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=FacilityTransferResponse.model_validate(transfer),
        message="Sending facility confirmation recorded.",
    )


@router.post(
    "/transfers/{transfer_id}/confirm-receiver",
    response_model=ApiResponse[FacilityTransferResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def confirm_transfer_receiver(
    transfer_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[FacilityTransferResponse]:
    """Confirmation from the RECEIVING facility. A transfer only completes
    once both this and /confirm-sender have been called (PRR 3.6)."""
    transfer = await service.confirm_transfer_receiver(
        transfer_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=FacilityTransferResponse.model_validate(transfer),
        message="Receiving facility confirmation recorded.",
    )


@router.post(
    "/transfers/{transfer_id}/cancel",
    response_model=ApiResponse[FacilityTransferResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def cancel_transfer(
    transfer_id: uuid.UUID,
    payload: FacilityTransferCancel,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[FacilityTransferResponse]:
    """Cancels a transfer at any point before Completed. A reason is mandatory."""
    transfer = await service.cancel_transfer(
        transfer_id,
        payload.reason,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=FacilityTransferResponse.model_validate(transfer),
        message="Transfer cancelled.",
    )


@router.post(
    "/care-logs",
    response_model=ApiResponse[DailyCareLogResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def submit_daily_care_log(
    payload: DailyCareLogCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[DailyCareLogResponse]:
    care_log = await service.submit_daily_care_log(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=DailyCareLogResponse.model_validate(care_log),
        message=("Daily care operational updates recorded successfully."),
    )


@router.get(
    "/dogs/{dog_id}/care-logs",
    response_model=ApiResponse[list[DailyCareLogResponse]],
    dependencies=[Depends(require_permission("shelter:read"))],
)
async def list_care_logs(
    dog_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[list[DailyCareLogResponse]]:
    logs = await service.list_care_logs(dog_id)
    return ApiResponse(
        data=[DailyCareLogResponse.model_validate(log) for log in logs],
    )


@router.delete(
    "/facilities/{facility_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def delete_facility(
    facility_id: uuid.UUID,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[None]:
    await service.soft_delete_facility(facility_id)
    return ApiResponse(message="Shelter facility deleted.")


@router.put(
    "/facilities/{facility_id}/status",
    response_model=ApiResponse[ShelterFacilityResponse],
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def update_facility_status(
    facility_id: uuid.UUID,
    payload: FacilityStatusUpdate,
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterFacilityResponse]:
    facility = await service.update_facility_status(
        facility_id,
        payload.status,
    )
    return ApiResponse(
        data=ShelterFacilityResponse.model_validate(facility),
        message="Facility status updated.",
    )


@router.post(
    "/facilities/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_delete_facilities(
    payload: BulkDeleteRequest,
    service: ShelterService = Depends(get_shelter_service),
) -> BulkDeleteResponse:
    deleted = await service.bulk_delete_facilities(
        payload.ids,
    )
    return BulkDeleteResponse(
        message=f"{deleted} facilities deleted.",
        deleted_count=deleted,
    )


@router.post(
    "/facilities/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def bulk_update_facility_status(
    payload: BulkStatusUpdateRequest,
    service: ShelterService = Depends(get_shelter_service),
) -> BulkStatusUpdateResponse:
    updated = await service.bulk_update_facility_status(
        payload.ids,
        parse_enum(FacilityStatus, payload.status),
    )
    return BulkStatusUpdateResponse(
        message=f"{updated} facilities updated.",
        updated_count=updated,
    )


# --- Shelter Vet Check Request Endpoints ---


@router.post(
    "/dogs/{dog_id}/request-vet-check",
    response_model=ApiResponse[ShelterVetCheckResponse],
    status_code=status.HTTP_201_CREATED,
)
async def request_shelter_vet_check(
    dog_id: uuid.UUID,
    payload: ShelterVetCheckRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterVetCheckResponse]:
    """Request a veterinary examination for a shelter dog.

    Available to: shelter_manager, rescue_centre_admin, super_admin.
    Does NOT require medical:create or appointment:create permissions.
    """
    from pawguard.modules.auth.rbac import has_permission

    # Inline RBAC: allow shelter_manager, rescue_centre_admin, super_admin
    is_authorized = (
        has_permission(current_user.user, "shelter:update")
        or has_permission(current_user.user, "shelter:read")
        or any(
            r in {"shelter_manager", "rescue_centre_admin", "super_admin", "system:admin"}
            for r in (current_user.claims.roles or [])
        )
    )
    if not is_authorized:
        from pawguard.modules.auth.exceptions import InsufficientPermissionsError

        raise InsufficientPermissionsError(
            "Missing required permission: shelter:update or shelter_manager role"
        )

    actor_roles = set(current_user.claims.roles)
    if hasattr(current_user.user, "roles") and current_user.user.roles:
        actor_roles.update(r.name for r in current_user.user.roles)

    ip = request.client.host if request.client else None
    vet_request = await service.request_vet_check(
        dog_id,
        payload,
        actor_id=current_user.user.id,
        actor_roles=actor_roles,
        ip_address=ip,
    )
    return ApiResponse(
        data=ShelterVetCheckResponse.model_validate(vet_request),
        message="Veterinary examination request created successfully.",
    )


@router.get(
    "/medical-requests",
    response_model=ApiResponse[list[ShelterVetRequestListResponse]],
)
async def list_shelter_medical_requests(
    current_user: CurrentUser = Depends(get_current_user),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[list[ShelterVetRequestListResponse]]:
    """List shelter veterinary requests.

    Veterinarians see requests assigned to them.
    Shelter managers/admins see requests for their facility.
    Super admins see all requests.
    """

    actor_roles = set(current_user.claims.roles)
    if hasattr(current_user.user, "roles") and current_user.user.roles:
        actor_roles.update(r.name for r in current_user.user.roles)

    parsed_status = None
    if status_filter:
        parsed_status = parse_enum(ShelterVetRequestStatus, status_filter, field_name="status")

    # Veterinarians see requests assigned to them
    if "veterinarian" in actor_roles:
        enriched = await service.list_vet_requests_for_vet(
            current_user.user.id, status=parsed_status
        )
        return ApiResponse(
            data=[ShelterVetRequestListResponse(**item) for item in enriched],
        )

    # Facility-scoped users see requests for their facility
    user = current_user.user
    if user.managed_facility_id and (
        "shelter_manager" in actor_roles or "rescue_centre_admin" in actor_roles
    ):
        enriched = await service.list_vet_requests_for_facility(
            user.managed_facility_id, status=parsed_status
        )
        return ApiResponse(
            data=[ShelterVetRequestListResponse(**item) for item in enriched],
        )

    # Super admins see all
    if "super_admin" in actor_roles or "system:admin" in actor_roles:
        # For super_admin, list all facilities' requests
        from pawguard.modules.shelter.repository import ShelterRepository

        repo = ShelterRepository(current_user.db)
        all_facilities = await repo.list_facilities()
        all_requests: list[dict] = []
        for facility in all_facilities:
            facility_requests = await service.list_vet_requests_for_facility(
                facility.id, status=parsed_status
            )
            all_requests.extend(facility_requests)
        return ApiResponse(
            data=[ShelterVetRequestListResponse(**item) for item in all_requests],
        )

    from pawguard.core.exceptions import ForbiddenError

    raise ForbiddenError("You do not have permission to view shelter medical requests.")


@router.patch(
    "/medical-requests/{request_id}/status",
    response_model=ApiResponse[ShelterVetCheckResponse],
)
async def update_shelter_medical_request_status(
    request_id: uuid.UUID,
    request_body: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: ShelterService = Depends(get_shelter_service),
) -> ApiResponse[ShelterVetCheckResponse]:
    """Update the status of a shelter veterinary request.

    Veterinarians can accept/complete/reject requests assigned to them.
    Shelter managers can cancel requests for their facility.
    """
    from pydantic import BaseModel

    class StatusUpdate(BaseModel):
        status: str

    body = await request_body.json()
    new_status_str = body.get("status")
    if not new_status_str:
        from pawguard.core.exceptions import ValidationFailedError

        raise ValidationFailedError("status field is required.")

    new_status = parse_enum(ShelterVetRequestStatus, new_status_str, field_name="status")

    actor_roles = set(current_user.claims.roles)
    if hasattr(current_user.user, "roles") and current_user.user.roles:
        actor_roles.update(r.name for r in current_user.user.roles)

    ip = request_body.client.host if request_body.client else None
    updated = await service.update_vet_request_status(
        request_id,
        new_status,
        actor_id=current_user.user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=ShelterVetCheckResponse.model_validate(updated),
        message=f"Request status updated to {new_status}.",
    )
