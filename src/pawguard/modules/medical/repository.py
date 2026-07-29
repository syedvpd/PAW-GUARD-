"""Data access for the Medical, Surgical & Veterinary Suite module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.medical.models import ClinicalExam, MedicalTreatment, Prescription, VaccinationRecord


class MedicalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_clinical_exam(self, exam: ClinicalExam) -> ClinicalExam:
        self._session.add(exam)
        await self._session.flush()
        return exam

    async def create_treatment(self, treatment: MedicalTreatment) -> MedicalTreatment:
        self._session.add(treatment)
        await self._session.flush()
        return treatment

    async def create_vaccination(self, rec: VaccinationRecord) -> VaccinationRecord:
        self._session.add(rec)
        await self._session.flush()
        return rec

    async def create_prescription(self, prescription: Prescription) -> Prescription:
        self._session.add(prescription)
        await self._session.flush()
        return prescription

    async def get_prescription_by_id(self, p_id: uuid.UUID) -> Prescription | None:
        stmt = select(Prescription).where(Prescription.id == p_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_exams_by_dog(self, dog_id: uuid.UUID) -> Sequence[ClinicalExam]:
        stmt = select(ClinicalExam).where(ClinicalExam.dog_id == dog_id).order_by(ClinicalExam.exam_date.desc())
        return (await self._session.execute(stmt)).scalars().all()

    async def get_treatments_by_dog(self, dog_id: uuid.UUID) -> Sequence[MedicalTreatment]:
        stmt = select(MedicalTreatment).where(MedicalTreatment.dog_id == dog_id).order_by(MedicalTreatment.treatment_date.desc())
        return (await self._session.execute(stmt)).scalars().all()

    async def get_vaccinations_by_dog(self, dog_id: uuid.UUID) -> Sequence[VaccinationRecord]:
        stmt = select(VaccinationRecord).where(VaccinationRecord.dog_id == dog_id).order_by(VaccinationRecord.administered_at.desc())
        return (await self._session.execute(stmt)).scalars().all()

    async def get_prescriptions_by_dog(self, dog_id: uuid.UUID) -> Sequence[Prescription]:
        stmt = select(Prescription).where(Prescription.dog_id == dog_id).order_by(Prescription.start_at.desc())
        return (await self._session.execute(stmt)).scalars().all()

    async def list_active_prescriptions(self) -> Sequence[Prescription]:
        stmt = select(Prescription).where(Prescription.is_active == True)
        return (await self._session.execute(stmt)).scalars().all()
