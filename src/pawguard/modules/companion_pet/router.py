"""Versioned companion pet API. Routes authenticate, authorize and delegate."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams, page_params
from pawguard.core.rate_limiter import rate_limit, resolve_client_ip
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.companion_pet.models import AppointmentStatus
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.schemas import (
    AppointmentCancelRequest,
    ClinicMembershipCreate,
    CompanionPetCreate,
    CompanionPetResponse,
    CompanionPetUpdate,
    MedicalRecordCreate,
    MedicalRecordResponse,
    MedicalUploadRequest,
    PetAppointmentCreate,
    PetAppointmentResponse,
    PetReminderCreate,
    PetReminderResponse,
    SafetyTagProvisionResponse,
    SafetyTagResponse,
    SafetyTagScanRequest,
    SafetyTagScanResponse,
    VetClinicCreate,
    VetClinicResponse,
    VetClinicUpdate,
    VeterinarianResponse,
)
from pawguard.modules.companion_pet.service import CompanionPetService
from pawguard.modules.storage.repository import StorageRepository
from pawguard.modules.storage.schemas import StoredFileResponse, UploadUrlResponse
from pawguard.modules.storage.service import StorageService
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService as S3StorageService

router = APIRouter(prefix="/companion-pets", tags=["companion-pets"])


def get_companion_pet_service(
    db: AsyncSession = Depends(get_db), audit: AuditService = Depends(get_audit_service)
) -> CompanionPetService:
    storage = StorageService(StorageRepository(db), S3StorageService())
    return CompanionPetService(CompanionPetRepository(db), db, storage=storage, audit=audit)


@router.post(
    "",
    response_model=ApiResponse[CompanionPetResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("companion_pet:create"))],
    summary="Create an owner companion pet",
)
async def create_pet(
    payload: CompanionPetCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[CompanionPetResponse]:
    pet = await service.create_pet(payload, current_user, resolve_client_ip(request))
    return ApiResponse(
        data=CompanionPetResponse.model_validate(pet), message="Companion pet created."
    )


@router.get(
    "",
    response_model=PaginatedResponse[CompanionPetResponse],
    dependencies=[Depends(require_permission("companion_pet:read"))],
    summary="List companion pets visible to the caller",
)
async def list_pets(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> PaginatedResponse[CompanionPetResponse]:
    return await service.list_pets(page, sort, current_user)


@router.get(
    "/clinics",
    response_model=PaginatedResponse[VetClinicResponse],
    summary="List active veterinary clinics",
)
async def list_clinics(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, max_length=128),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> PaginatedResponse[VetClinicResponse]:
    return await service.list_clinics(page, sort, search)


@router.get(
    "/clinics/{clinic_id}/veterinarians",
    response_model=ApiResponse[list[VeterinarianResponse]],
    dependencies=[Depends(require_permission("appointment:read"))],
    summary="List veterinarians available at a veterinary clinic",
)
async def list_clinic_veterinarians(
    clinic_id: uuid.UUID,
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[list[VeterinarianResponse]]:
    vets = await service.list_clinic_veterinarians(clinic_id)
    return ApiResponse(data=vets)


@router.get(
    "/appointments",
    response_model=PaginatedResponse[PetAppointmentResponse],
    dependencies=[Depends(require_permission("appointment:read"))],
    summary="List authorized veterinary appointments",
)
async def list_appointments(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    clinic_id: uuid.UUID | None = Query(None),
    pet_id: uuid.UUID | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> PaginatedResponse[PetAppointmentResponse]:
    return await service.list_appointments(page, sort, current_user, clinic_id, pet_id)


@router.get(
    "/{pet_id}",
    response_model=ApiResponse[CompanionPetResponse],
    dependencies=[Depends(require_permission("companion_pet:read"))],
    summary="Get an authorized companion pet profile",
)
async def get_pet(
    pet_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[CompanionPetResponse]:
    pet = await service.get_pet(pet_id, current_user)
    return ApiResponse(data=CompanionPetResponse.model_validate(pet))


@router.patch(
    "/{pet_id}",
    response_model=ApiResponse[CompanionPetResponse],
    dependencies=[Depends(require_permission("companion_pet:update"))],
    summary="Update an authorized companion pet profile",
)
async def update_pet(
    pet_id: uuid.UUID,
    payload: CompanionPetUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[CompanionPetResponse]:
    pet = await service.update_pet(pet_id, payload, current_user, resolve_client_ip(request))
    return ApiResponse(
        data=CompanionPetResponse.model_validate(pet), message="Companion pet updated."
    )


@router.delete(
    "/{pet_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("companion_pet:delete"))],
    summary="Soft-delete an owned companion pet",
)
async def delete_pet(
    pet_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[None]:
    await service.delete_pet(pet_id, current_user, resolve_client_ip(request))
    return ApiResponse(message="Companion pet deleted.")


@router.post(
    "/{pet_id}/medical-files/upload-url",
    response_model=ApiResponse[UploadUrlResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("companion_pet:medical_upload"))],
    summary="Request a presigned medical-history upload",
)
async def request_medical_upload(
    pet_id: uuid.UUID,
    payload: MedicalUploadRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[UploadUrlResponse]:
    result = await service.request_medical_upload(
        pet_id,
        original_filename=payload.original_filename,
        mime_type=payload.mime_type,
        file_size=payload.file_size,
        current_user=current_user,
    )
    return ApiResponse(data=result, message="Medical upload URL generated.")


@router.put(
    "/{pet_id}/medical-files/{file_id}/confirm",
    response_model=ApiResponse[StoredFileResponse],
    dependencies=[Depends(require_permission("companion_pet:medical_upload"))],
    summary="Confirm a medical-history upload",
)
async def confirm_medical_upload(
    pet_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[StoredFileResponse]:
    stored = await service.confirm_medical_upload(pet_id, file_id, current_user)
    return ApiResponse(data=StoredFileResponse.model_validate(stored))


@router.get(
    "/{pet_id}/medical-files",
    response_model=PaginatedResponse[StoredFileResponse],
    dependencies=[Depends(require_permission("companion_pet:read"))],
    summary="List authorized medical-history files",
)
async def list_medical_files(
    pet_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> PaginatedResponse[StoredFileResponse]:
    return await service.list_medical_files(pet_id, page, sort, current_user)


@router.post(
    "/{pet_id}/medical-records",
    response_model=ApiResponse[MedicalRecordResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("companion_pet:medical_upload"))],
    summary="Create a medical-history record",
)
async def create_medical_record(
    pet_id: uuid.UUID,
    payload: MedicalRecordCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[MedicalRecordResponse]:
    record = await service.create_medical_record(
        pet_id, payload, current_user, resolve_client_ip(request)
    )
    return ApiResponse(data=MedicalRecordResponse.model_validate(record))


@router.get(
    "/{pet_id}/medical-records",
    response_model=ApiResponse[list[MedicalRecordResponse]],
    dependencies=[Depends(require_permission("companion_pet:read"))],
    summary="List a pet's authorized medical history",
)
async def list_medical_records(
    pet_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[list[MedicalRecordResponse]]:
    records = await service.list_medical_records(pet_id, current_user)
    return ApiResponse(data=[MedicalRecordResponse.model_validate(row) for row in records])


@router.delete(
    "/medical-records/{record_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("companion_pet:medical_upload"))],
    summary="Soft-delete an authorized medical-history record",
)
async def delete_medical_record(
    record_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[None]:
    await service.delete_medical_record(record_id, current_user, resolve_client_ip(request))
    return ApiResponse(message="Medical record deleted.")


@router.post(
    "/{pet_id}/safety-tag",
    response_model=ApiResponse[SafetyTagProvisionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("safety_tag:manage"))],
    summary="Provision or rotate a QR safety tag",
)
async def provision_safety_tag(
    pet_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[SafetyTagProvisionResponse]:
    tag, raw_token = await service.provision_safety_tag(
        pet_id, current_user, resolve_client_ip(request)
    )
    data = SafetyTagProvisionResponse(
        **SafetyTagResponse.model_validate(tag).model_dump(),
        raw_token=raw_token,
    )
    return ApiResponse(data=data, message="Safety tag provisioned. Store the token in the QR code.")


@router.get(
    "/{pet_id}/safety-tag",
    response_model=ApiResponse[SafetyTagResponse],
    dependencies=[Depends(require_permission("companion_pet:read"))],
    summary="Read safety-tag metadata without revealing its token",
)
async def get_safety_tag(
    pet_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[SafetyTagResponse]:
    tag = await service.get_safety_tag(pet_id, current_user)
    if tag is None:
        return ApiResponse(data=None, message="No active safety tag.")
    return ApiResponse(data=SafetyTagResponse.model_validate(tag))


@router.post(
    "/safety-tag/scan",
    response_model=ApiResponse[SafetyTagScanResponse],
    dependencies=[Depends(rate_limit("safety_tag_scan", max_requests=20, window_seconds=60))],
    summary="Privacy-safe public QR safety-tag scan",
)
async def scan_safety_tag(
    payload: SafetyTagScanRequest,
    request: Request,
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[SafetyTagScanResponse]:
    _tag, pet = await service.scan_safety_tag(payload.token, resolve_client_ip(request))
    photo_url = await service.get_pet_photo_url(pet.id)
    return ApiResponse(
        data=SafetyTagScanResponse(
            pet_id=pet.id,
            name=pet.name,
            species=pet.species,
            breed=pet.breed,
            color=pet.color,
            emergency_notes=pet.emergency_notes,
            photo_url=photo_url,
        )
    )


@router.post(
    "/clinics",
    response_model=ApiResponse[VetClinicResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("vet_clinic:manage"))],
    summary="Create a veterinary clinic directory entry",
)
async def create_clinic(
    payload: VetClinicCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[VetClinicResponse]:
    clinic = await service.create_clinic(payload, current_user, resolve_client_ip(request))
    return ApiResponse(data=VetClinicResponse.model_validate(clinic))


@router.patch(
    "/clinics/{clinic_id}",
    response_model=ApiResponse[VetClinicResponse],
    dependencies=[Depends(require_permission("vet_clinic:manage"))],
    summary="Update a veterinary clinic directory entry",
)
async def update_clinic(
    clinic_id: uuid.UUID,
    payload: VetClinicUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[VetClinicResponse]:
    clinic = await service.update_clinic(
        clinic_id, payload, current_user, resolve_client_ip(request)
    )
    return ApiResponse(data=VetClinicResponse.model_validate(clinic))


@router.delete(
    "/clinics/{clinic_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("vet_clinic:manage"))],
    summary="Soft-delete a veterinary clinic directory entry",
)
async def delete_clinic(
    clinic_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[None]:
    await service.delete_clinic(clinic_id, current_user, resolve_client_ip(request))
    return ApiResponse(message="Veterinary clinic deleted.")


@router.post(
    "/clinics/{clinic_id}/memberships",
    response_model=ApiResponse[None],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("vet_clinic:manage"))],
    summary="Authorize a user for a veterinary clinic",
)
async def add_clinic_membership(
    clinic_id: uuid.UUID,
    payload: ClinicMembershipCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[None]:
    await service.add_membership(clinic_id, payload.membership_role, payload.user_id, current_user)
    return ApiResponse(message="Clinic membership created.")


@router.post(
    "/appointments",
    response_model=ApiResponse[PetAppointmentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("appointment:create"))],
    summary="Book a veterinary appointment",
)
async def create_appointment(
    payload: PetAppointmentCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[PetAppointmentResponse]:
    appointment = await service.create_appointment(
        payload, current_user, resolve_client_ip(request)
    )
    return ApiResponse(data=PetAppointmentResponse.model_validate(appointment))


@router.get(
    "/appointments/{appointment_id}",
    response_model=ApiResponse[PetAppointmentResponse],
    dependencies=[Depends(require_permission("appointment:read"))],
    summary="Get an authorized appointment",
)
async def get_appointment(
    appointment_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[PetAppointmentResponse]:
    appointment = await service.get_appointment(appointment_id, current_user)
    return ApiResponse(data=PetAppointmentResponse.model_validate(appointment))


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=ApiResponse[PetAppointmentResponse],
    dependencies=[Depends(require_permission("appointment:cancel"))],
    summary="Cancel an appointment",
)
async def cancel_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentCancelRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[PetAppointmentResponse]:
    appointment = await service.cancel_appointment(
        appointment_id, payload.reason, current_user, resolve_client_ip(request)
    )
    return ApiResponse(data=PetAppointmentResponse.model_validate(appointment))


@router.post(
    "/appointments/{appointment_id}/confirm",
    response_model=ApiResponse[PetAppointmentResponse],
    dependencies=[Depends(require_permission("appointment:manage"))],
    summary="Confirm an appointment as clinic staff",
)
async def confirm_appointment(
    appointment_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[PetAppointmentResponse]:
    appointment = await service.update_appointment_status(
        appointment_id, AppointmentStatus.CONFIRMED, current_user, resolve_client_ip(request)
    )
    return ApiResponse(data=PetAppointmentResponse.model_validate(appointment))


@router.post(
    "/{pet_id}/reminders",
    response_model=ApiResponse[PetReminderResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("companion_pet:update"))],
    summary="Create a vaccination or medication reminder",
)
async def create_reminder(
    pet_id: uuid.UUID,
    payload: PetReminderCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[PetReminderResponse]:
    reminder = await service.create_reminder(pet_id, payload, current_user)
    return ApiResponse(data=PetReminderResponse.model_validate(reminder))


@router.get(
    "/{pet_id}/reminders",
    response_model=ApiResponse[list[PetReminderResponse]],
    dependencies=[Depends(require_permission("companion_pet:read"))],
    summary="List vaccination and medication reminders",
)
async def list_reminders(
    pet_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[list[PetReminderResponse]]:
    reminders = await service.list_reminders(pet_id, current_user)
    return ApiResponse(data=[PetReminderResponse.model_validate(row) for row in reminders])


@router.delete(
    "/{pet_id}/reminders/{reminder_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("companion_pet:update"))],
    summary="Soft-delete a vaccination or medication reminder",
)
async def delete_reminder(
    pet_id: uuid.UUID,
    reminder_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CompanionPetService = Depends(get_companion_pet_service),
) -> ApiResponse[None]:
    await service.delete_reminder(pet_id, reminder_id, current_user)
    return ApiResponse(message="Reminder deleted.")
