"""Pydantic schemas for the Medical module."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.inventory.schemas import InventoryConsumptionItem


class ClinicalExamCreate(BaseModel):
    dog_id: uuid.UUID
    body_condition_score: int = Field(..., ge=1, le=9, examples=[5])
    dental_health: str | None = Field(None, max_length=64, examples=["Mild tartar buildup"])
    ocular_aural_notes: str | None = Field(None, examples=["Clear, no discharge."])
    coat_condition: str | None = Field(
        None, max_length=128, examples=["Slightly matted, otherwise healthy"]
    )
    visible_injuries: str | None = Field(None, examples=["Small laceration on left hind leg."])
    triage_diagnosis: str = Field(..., min_length=1, examples=["Stable, mild dehydration"])


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
    treatment_type: str = Field(..., min_length=1, max_length=128, examples=["Spay/Neuter Surgery"])
    description: str = Field(
        ..., min_length=1, examples=["Routine spay procedure, no complications."]
    )
    anesthesia_log: str | None = Field(None, examples=["Isoflurane, 45 minutes, stable vitals."])
    post_op_notes: str | None = Field(None, examples=["Recovering well, monitor incision site."])
    inventory_consumptions: list[InventoryConsumptionItem] | None = Field(
        None, examples=[[{"item_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "quantity": 2.0}]]
    )


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
    vaccine_name: str = Field(..., min_length=1, max_length=128, examples=["Rabies"])
    next_due_at: datetime | None = Field(None, examples=["2027-07-22T00:00:00Z"])
    lot_number: str | None = Field(None, max_length=64, examples=["LOT-48213"])


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
    drug_name: str = Field(..., min_length=1, max_length=128, examples=["Amoxicillin"])
    dosage: str = Field(..., min_length=1, max_length=128, examples=["250mg twice daily"])
    route: str = Field(..., min_length=1, max_length=64, examples=["Oral"])
    start_at: datetime = Field(..., examples=["2026-07-22T08:00:00Z"])
    end_at: datetime = Field(..., examples=["2026-07-29T08:00:00Z"])
    inventory_consumptions: list[InventoryConsumptionItem] | None = Field(
        None, examples=[[{"item_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "quantity": 1.0}]]
    )


class PrescriptionUpdate(BaseModel):
    drug_name: str | None = Field(None, min_length=1, max_length=128, examples=["Amoxicillin"])
    dosage: str | None = Field(None, min_length=1, max_length=128, examples=["250mg twice daily"])
    route: str | None = Field(None, min_length=1, max_length=64, examples=["Oral"])
    start_at: datetime | None = Field(None, examples=["2026-07-22T08:00:00Z"])
    end_at: datetime | None = Field(None, examples=["2026-07-29T08:00:00Z"])
    is_active: bool | None = Field(None, examples=[True])


class PrescriptionStatusUpdate(BaseModel):
    is_active: bool = Field(
        ..., description="Set prescription active or inactive", examples=[False]
    )


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


class MedicationAdministrationCreate(BaseModel):
    prescription_id: uuid.UUID | None = Field(
        None, description="Prescription this sign-off belongs to, if any."
    )
    dog_id: uuid.UUID
    medication_name: str = Field(..., min_length=1, max_length=128, examples=["Amoxicillin"])
    dosage: str = Field(..., min_length=1, max_length=128, examples=["5ml"])
    route: str = Field(..., min_length=1, max_length=64, examples=["Oral"])
    administered_at: datetime | None = Field(None, examples=["2026-07-29T10:00:00Z"])
    notes: str | None = Field(None, examples=["Given with food, tolerated well."])


class MedicationAdministrationResponse(BaseModel):
    id: uuid.UUID
    prescription_id: uuid.UUID | None
    dog_id: uuid.UUID
    medication_name: str
    dosage: str
    route: str
    administered_at: datetime
    administered_by_id: uuid.UUID
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VaccineProtocolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, examples=["Rabies"])
    default_interval_days: int = Field(..., ge=1, le=3650, examples=[365])
    is_required: bool = Field(True, examples=[True])


class VaccineProtocolResponse(BaseModel):
    id: uuid.UUID
    name: str
    default_interval_days: int
    is_required: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MedicalClearanceCreate(BaseModel):
    clearance_type: str = Field(
        default="adoption_surgery",
        min_length=1,
        max_length=64,
        examples=["adoption_surgery"],
    )
    status: Literal["approved", "denied", "pending"] = Field("approved", examples=["approved"])
    decision_notes: str | None = Field(None, examples=["Healthy, cleared for adoption."])
    expires_at: datetime | None = Field(None, examples=["2026-08-03T00:00:00Z"])


class MedicalClearanceResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    authorized_by_id: uuid.UUID
    clearance_type: str
    status: str
    decision_notes: str | None
    authorized_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
