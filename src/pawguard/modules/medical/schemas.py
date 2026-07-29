"""Pydantic schemas for the Medical module."""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ClinicalExamCreate(BaseModel):
    dog_id: uuid.UUID
    body_condition_score: int = Field(..., ge=1, le=9)
    dental_health: str | None = Field(None, max_length=64)
    ocular_aural_notes: str | None = None
    coat_condition: str | None = Field(None, max_length=128)
    visible_injuries: str | None = None
    triage_diagnosis: str = Field(..., min_length=1)


class ClinicalExamResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    vet_id: uuid.UUID
    exam_date: datetime
    body_condition_score: int
    dental_health: str | None
    ocular_aural_notes: str | None
    coat_condition: str | None
    visible_injuries: str | None
    triage_diagnosis: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MedicalTreatmentCreate(BaseModel):
    dog_id: uuid.UUID
    treatment_type: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    anesthesia_log: str | None = None
    post_op_notes: str | None = None


class MedicalTreatmentResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    vet_id: uuid.UUID
    treatment_date: datetime
    treatment_type: str
    description: str
    anesthesia_log: str | None
    post_op_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VaccinationRecordCreate(BaseModel):
    dog_id: uuid.UUID
    vaccine_name: str = Field(..., min_length=1, max_length=128)
    next_due_at: datetime | None = None
    lot_number: str | None = Field(None, max_length=64)


class VaccinationRecordResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    administered_by: uuid.UUID
    vaccine_name: str
    administered_at: datetime
    next_due_at: datetime | None
    lot_number: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrescriptionCreate(BaseModel):
    dog_id: uuid.UUID
    drug_name: str = Field(..., min_length=1, max_length=128)
    dosage: str = Field(..., min_length=1, max_length=128)
    route: str = Field(..., min_length=1, max_length=64)
    start_at: datetime
    end_at: datetime


class PrescriptionResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    vet_id: uuid.UUID
    drug_name: str
    dosage: str
    route: str
    start_at: datetime
    end_at: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
