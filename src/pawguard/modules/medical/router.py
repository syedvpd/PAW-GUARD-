"""API router for the Medical, Surgical & Veterinary Suite module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Sequence
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import get_current_user, CurrentUser
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.medical.repository import MedicalRepository
from pawguard.modules.medical.schemas import (
    ClinicalExamCreate,
    ClinicalExamResponse,
    MedicalTreatmentCreate,
    MedicalTreatmentResponse,
    PrescriptionCreate,
    PrescriptionResponse,
    VaccinationRecordCreate,
    VaccinationRecordResponse,
)
from pawguard.modules.medical.service import MedicalService

router = APIRouter(prefix="/medical", tags=["medical"])


def get_medical_service(db: AsyncSession = Depends(get_db)) -> MedicalService:
    repo = MedicalRepository(db)
    dog_repo = DogRepository(db)
    return MedicalService(repo, dog_repo)


@router.post(
    "/exams",
    response_model=ApiResponse[ClinicalExamResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:write"))],
)
async def perform_clinical_exam(
    payload: ClinicalExamCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[ClinicalExamResponse]:
    exam = await service.perform_clinical_exam(current_user.user.id, payload)
    return ApiResponse(
        data=ClinicalExamResponse.model_validate(exam),
        message="Clinical examination logged successfully.",
    )


@router.post(
    "/treatments",
    response_model=ApiResponse[MedicalTreatmentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:write"))],
)
async def record_treatment(
    payload: MedicalTreatmentCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[MedicalTreatmentResponse]:
    treatment = await service.record_treatment(current_user.user.id, payload)
    return ApiResponse(
        data=MedicalTreatmentResponse.model_validate(treatment),
        message="Medical treatment / surgery logged successfully.",
    )


@router.post(
    "/vaccinations",
    response_model=ApiResponse[VaccinationRecordResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:write"))],
)
async def administer_vaccine(
    payload: VaccinationRecordCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[VaccinationRecordResponse]:
    rec = await service.administer_vaccine(current_user.user.id, payload)
    return ApiResponse(
        data=VaccinationRecordResponse.model_validate(rec),
        message="Vaccination details logged successfully.",
    )


@router.post(
    "/prescriptions",
    response_model=ApiResponse[PrescriptionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:write"))],
)
async def prescribe_medication(
    payload: PrescriptionCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[PrescriptionResponse]:
    prescription = await service.prescribe_medication(current_user.user.id, payload)
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
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[bool]:
    roles = {r.name for r in current_user.user.roles}
    success = await service.authorize_adoption_clearance(dog_id, roles)
    return ApiResponse(
        data=success,
        message="Adoption medical clearance granted successfully.",
    )


@router.get(
    "/dogs/{dog_id}/history",
    response_model=ApiResponse[dict],
)
async def get_medical_history(
    dog_id: uuid.UUID,
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[dict]:
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
