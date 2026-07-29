"""MedicalService: owns all medical examinations, surgeries, prescriptions, and clearances behavior (RULE-003)."""

import uuid
from datetime import UTC, datetime
from typing import Sequence

from pawguard.core.exceptions import NotFoundError, ForbiddenError
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.medical.models import ClinicalExam, MedicalTreatment, Prescription, VaccinationRecord
from pawguard.modules.medical.repository import MedicalRepository
from pawguard.modules.medical.schemas import (
    ClinicalExamCreate,
    MedicalTreatmentCreate,
    PrescriptionCreate,
    VaccinationRecordCreate,
)


class MedicalService:
    def __init__(self, repository: MedicalRepository, dog_repo: DogRepository) -> None:
        self._repo = repository
        self._dog_repo = dog_repo

    async def perform_clinical_exam(self, vet_id: uuid.UUID, payload: ClinicalExamCreate) -> ClinicalExam:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        exam = ClinicalExam(
            dog_id=payload.dog_id,
            vet_id=vet_id,
            exam_date=datetime.now(UTC),
            body_condition_score=payload.body_condition_score,
            dental_health=payload.dental_health,
            ocular_aural_notes=payload.ocular_aural_notes,
            coat_condition=payload.coat_condition,
            visible_injuries=payload.visible_injuries,
            triage_diagnosis=payload.triage_diagnosis,
        )
        return await self._repo.create_clinical_exam(exam)

    async def record_treatment(self, vet_id: uuid.UUID, payload: MedicalTreatmentCreate) -> MedicalTreatment:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        treatment = MedicalTreatment(
            dog_id=payload.dog_id,
            vet_id=vet_id,
            treatment_date=datetime.now(UTC),
            treatment_type=payload.treatment_type,
            description=payload.description,
            anesthesia_log=payload.anesthesia_log,
            post_op_notes=payload.post_op_notes,
        )
        return await self._repo.create_treatment(treatment)

    async def administer_vaccine(self, vet_id: uuid.UUID, payload: VaccinationRecordCreate) -> VaccinationRecord:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        rec = VaccinationRecord(
            dog_id=payload.dog_id,
            administered_by=vet_id,
            vaccine_name=payload.vaccine_name,
            administered_at=datetime.now(UTC),
            next_due_at=payload.next_due_at,
            lot_number=payload.lot_number,
        )
        return await self._repo.create_vaccination(rec)

    async def prescribe_medication(self, vet_id: uuid.UUID, payload: PrescriptionCreate) -> Prescription:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        prescription = Prescription(
            dog_id=payload.dog_id,
            vet_id=vet_id,
            drug_name=payload.drug_name,
            dosage=payload.dosage,
            route=payload.route,
            start_at=payload.start_at,
            end_at=payload.end_at,
            is_active=True,
        )
        return await self._repo.create_prescription(prescription)

    async def authorize_adoption_clearance(self, dog_id: uuid.UUID, roles: set[str]) -> bool:
        # Business validation: user must possess clinical / admin credentials
        if not ("super_admin" in roles or "veterinarian" in roles):
            raise ForbiddenError("Adoption medical clearances require a veterinarian's authority.")

        dog = await self._dog_repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        dog.is_adoptable = True
        dog.is_quarantine_passed = True
        await self._dog_repo._session.flush()
        return True

    async def get_exams_for_dog(self, dog_id: uuid.UUID) -> Sequence[ClinicalExam]:
        return await self._repo.get_exams_by_dog(dog_id)

    async def get_treatments_for_dog(self, dog_id: uuid.UUID) -> Sequence[MedicalTreatment]:
        return await self._repo.get_treatments_by_dog(dog_id)

    async def get_vaccinations_for_dog(self, dog_id: uuid.UUID) -> Sequence[VaccinationRecord]:
        return await self._repo.get_vaccinations_by_dog(dog_id)

    async def get_prescriptions_for_dog(self, dog_id: uuid.UUID) -> Sequence[Prescription]:
        return await self._repo.get_prescriptions_by_dog(dog_id)
