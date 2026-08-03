"""API router for the Medical, Surgical & Veterinary Suite module.

Routers only validate and call services.
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
from pawguard.modules.medical.repository import MedicalRepository
from pawguard.modules.medical.schemas import (
    ClinicalExamCreate,
    ClinicalExamResponse,
    MedicalTreatmentCreate,
    MedicalTreatmentResponse,
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionStatusUpdate,
    PrescriptionUpdate,
    VaccinationRecordCreate,
    VaccinationRecordResponse,
)
from pawguard.modules.medical.service import MedicalService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/medical", tags=["medical"])


def get_medical_service(
    db: AsyncSession = Depends(get_db), audit: AuditService = Depends(get_audit_service),
) -> MedicalService:
    repo = MedicalRepository(db)
    dog_repo = DogRepository(db)
    inventory = InventoryService(InventoryRepository(db), audit_service=audit)
    return MedicalService(repo, dog_repo, audit_service=audit, inventory_service=inventory)


@router.post(
    "/exams",
    response_model=ApiResponse[ClinicalExamResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:create"))],
)
async def perform_clinical_exam(
    payload: ClinicalExamCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[ClinicalExamResponse]:
    ip = request.client.host if request.client else None
    exam = await service.perform_clinical_exam(
        current_user.user.id, payload, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=ClinicalExamResponse.model_validate(exam),
        message="Clinical examination logged successfully.",
    )


@router.post(
    "/treatments",
    response_model=ApiResponse[MedicalTreatmentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:create"))],
)
async def record_treatment(
    payload: MedicalTreatmentCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[MedicalTreatmentResponse]:
    ip = request.client.host if request.client else None
    treatment = await service.record_treatment(
        current_user.user.id, payload, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=MedicalTreatmentResponse.model_validate(treatment),
        message="Medical treatment / surgery logged successfully.",
    )


@router.post(
    "/vaccinations",
    response_model=ApiResponse[VaccinationRecordResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:create"))],
)
async def administer_vaccine(
    payload: VaccinationRecordCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[VaccinationRecordResponse]:
    ip = request.client.host if request.client else None
    rec = await service.administer_vaccine(
        current_user.user.id, payload, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=VaccinationRecordResponse.model_validate(rec),
        message="Vaccination details logged successfully.",
    )


@router.post(
    "/prescriptions",
    response_model=ApiResponse[PrescriptionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:create"))],
)
async def prescribe_medication(
    payload: PrescriptionCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[PrescriptionResponse]:
    ip = request.client.host if request.client else None
    prescription = await service.prescribe_medication(
        current_user.user.id, payload, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=PrescriptionResponse.model_validate(prescription),
        message="Medication prescription generated successfully.",
    )


@router.post(
    "/clearance/{dog_id}",
    response_model=ApiResponse[bool],
    dependencies=[Depends(require_permission("medical:clearance"))],
)
async def authorize_adoption_clearance(
    dog_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[bool]:
    roles = {r.name for r in current_user.user.roles}
    ip = request.client.host if request.client else None
    success = await service.authorize_adoption_clearance(
        dog_id, roles, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=success,
        message="Adoption medical clearance granted successfully.",
    )


@router.get(
    "/dogs/{dog_id}/history",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def get_medical_history(
    dog_id: uuid.UUID,
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[dict[str, Any]]:
    exams = await service.get_exams_for_dog(dog_id)
    treatments = await service.get_treatments_for_dog(dog_id)
    vaccinations = await service.get_vaccinations_for_dog(dog_id)
    prescriptions = await service.get_prescriptions_for_dog(dog_id)

    history = {
        "exams": [ClinicalExamResponse.model_validate(e) for e in exams],
        "treatments": [MedicalTreatmentResponse.model_validate(t) for t in treatments],
        "vaccinations": [VaccinationRecordResponse.model_validate(v) for v in vaccinations],
        "prescriptions": [PrescriptionResponse.model_validate(p) for p in prescriptions],
    }
    return ApiResponse(data=history)


@router.get(
    "/exams",
    response_model=PaginatedResponse[ClinicalExamResponse],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def list_exams(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by triage diagnosis"),
    dog_id: uuid.UUID | None = Query(None, description="Filter by dog ID"),
    vet_id: uuid.UUID | None = Query(None, description="Filter by vet ID"),
    service: MedicalService = Depends(get_medical_service),
) -> PaginatedResponse[ClinicalExamResponse]:
    return await service.list_exams_paginated(
        page=page, sort=sort, search_term=search, dog_id=dog_id, vet_id=vet_id,
    )


@router.get(
    "/treatments",
    response_model=PaginatedResponse[MedicalTreatmentResponse],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def list_treatments(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by treatment type"),
    dog_id: uuid.UUID | None = Query(None, description="Filter by dog ID"),
    vet_id: uuid.UUID | None = Query(None, description="Filter by vet ID"),
    service: MedicalService = Depends(get_medical_service),
) -> PaginatedResponse[MedicalTreatmentResponse]:
    return await service.list_treatments_paginated(
        page=page, sort=sort, search_term=search, dog_id=dog_id, vet_id=vet_id,
    )


@router.get(
    "/vaccinations",
    response_model=PaginatedResponse[VaccinationRecordResponse],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def list_vaccinations(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by vaccine name"),
    dog_id: uuid.UUID | None = Query(None, description="Filter by dog ID"),
    vet_id: uuid.UUID | None = Query(None, description="Filter by vet ID"),
    service: MedicalService = Depends(get_medical_service),
) -> PaginatedResponse[VaccinationRecordResponse]:
    return await service.list_vaccinations_paginated(
        page=page, sort=sort, search_term=search, dog_id=dog_id, vet_id=vet_id,
    )


@router.get(
    "/prescriptions",
    response_model=PaginatedResponse[PrescriptionResponse],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def list_prescriptions(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by drug name"),
    dog_id: uuid.UUID | None = Query(None, description="Filter by dog ID"),
    vet_id: uuid.UUID | None = Query(None, description="Filter by vet ID"),
    service: MedicalService = Depends(get_medical_service),
) -> PaginatedResponse[PrescriptionResponse]:
    return await service.list_prescriptions_paginated(
        page=page, sort=sort, search_term=search, dog_id=dog_id, vet_id=vet_id,
    )


@router.put(
    "/prescriptions/{prescription_id}",
    response_model=ApiResponse[PrescriptionResponse],
    dependencies=[Depends(require_permission("medical:update"))],
)
async def update_prescription(
    prescription_id: uuid.UUID,
    payload: PrescriptionUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[PrescriptionResponse]:
    ip = request.client.host if request.client else None
    prescription = await service.update_prescription(
        prescription_id, payload, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=PrescriptionResponse.model_validate(prescription),
        message="Prescription updated successfully.",
    )


@router.patch(
    "/prescriptions/{prescription_id}/status",
    response_model=ApiResponse[PrescriptionResponse],
    dependencies=[Depends(require_permission("medical:update"))],
)
async def update_prescription_status(
    prescription_id: uuid.UUID,
    payload: PrescriptionStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[PrescriptionResponse]:
    ip = request.client.host if request.client else None
    prescription = await service.update_prescription_status(
        prescription_id, payload.is_active, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=PrescriptionResponse.model_validate(prescription),
        message="Prescription status updated successfully.",
    )


@router.delete(
    "/{entity_type}/{entity_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("medical:delete"))],
)
async def soft_delete_entity(
    entity_type: str,
    entity_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[None]:
    type_map = {
        "exams": service.soft_delete_exam,
        "treatments": service.soft_delete_treatment,
        "vaccinations": service.soft_delete_vaccination,
        "prescriptions": service.soft_delete_prescription,
    }
    delete_fn = type_map.get(entity_type)
    if delete_fn is None:
        return ApiResponse(success=False, message=f"Unknown entity type: {entity_type}")
    ip = request.client.host if request.client else None
    await delete_fn(entity_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(message=f"{entity_type.rstrip('s').capitalize()} deleted successfully.")


@router.post(
    "/bulk/prescriptions/status",
    response_model=ApiResponse[BulkStatusUpdateResponse],
    dependencies=[Depends(require_permission("medical:update"))],
)
async def bulk_update_prescription_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[BulkStatusUpdateResponse]:
    is_active = payload.status.lower() == "active"
    ip = request.client.host if request.client else None
    updated = await service.bulk_update_prescription_status(
        payload.ids, is_active, actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=BulkStatusUpdateResponse(
            message=f"{updated} prescription(s) status updated.",
            updated_count=updated,
        ),
    )


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("medical:delete"))],
)
async def bulk_delete_entities(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[BulkDeleteResponse]:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_soft_delete(
        payload.ids, "prescriptions", actor_id=current_user.id, ip_address=ip,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} record(s) deleted.",
            deleted_count=deleted,
        ),
    )
