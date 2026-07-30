"""ORM models for the Medical, Surgical & Veterinary Suite module."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class ClinicalExam(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "clinical_exams"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    )
    vet_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    exam_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    body_condition_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-9 scale
    dental_health: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocular_aural_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    coat_condition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visible_injuries: Mapped[str | None] = mapped_column(Text, nullable=True)
    triage_diagnosis: Mapped[str] = mapped_column(Text, nullable=False)


class MedicalTreatment(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "medical_treatments"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    )
    vet_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    treatment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # surgery, therapy, dressing, etc.
    treatment_type: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    anesthesia_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_op_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class VaccinationRecord(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "vaccination_records"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    )
    administered_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # DHPP, Rabies, Dewormer, etc.
    vaccine_name: Mapped[str] = mapped_column(String(128), nullable=False)
    administered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lot_number: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Prescription(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "prescriptions"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    )
    vet_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    drug_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dosage: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g., "5ml" or "1 tablet"
    route: Mapped[str] = mapped_column(String(64), nullable=False)  # Oral, IV, IM, etc.
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
