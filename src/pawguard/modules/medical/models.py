"""ORM models for the Medical, Surgical & Veterinary Suite module."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class ClinicalExam(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "clinical_exams"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    vet_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    exam_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    body_condition_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-9 scale
    dental_health: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocular_aural_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    coat_condition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visible_injuries: Mapped[str | None] = mapped_column(Text, nullable=True)
    triage_diagnosis: Mapped[str] = mapped_column(Text, nullable=False)


class MedicalTreatment(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "medical_treatments"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    vet_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    treatment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # surgery, therapy, dressing, etc.
    treatment_type: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    anesthesia_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_op_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class VaccinationRecord(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "vaccination_records"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    administered_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )

    # DHPP, Rabies, Dewormer, etc.
    vaccine_name: Mapped[str] = mapped_column(String(128), nullable=False)
    administered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lot_number: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Prescription(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "prescriptions"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    vet_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )

    drug_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dosage: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g., "5ml" or "1 tablet"
    route: Mapped[str] = mapped_column(String(64), nullable=False)  # Oral, IV, IM, etc.
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MedicationAdministrationLog(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """Daily nurse sign-off register for medication administrations (PRR 3.5).

    Every administered dose is signed off against its prescription (when one
    exists) and dog, producing an immutable trail for the shift register.
    """

    __tablename__ = "medication_administration_logs"

    prescription_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prescriptions.id", ondelete="SET NULL"),
        nullable=True,
    
        index=True
    )
    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    medication_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dosage: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g., "5ml" or "1 tablet"
    route: Mapped[str] = mapped_column(String(64), nullable=False)  # Oral, IV, IM, etc.
    administered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    administered_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class VaccineProtocol(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """Optional, staff-managed protocol that drives vaccination auto-scheduling.

    The table is intentionally optional: lookups are nullable so environments
    that have not yet provisioned protocols keep working without auto-schedule.
    """

    __tablename__ = "vaccine_protocols"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    default_interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class MedicalClearance(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """Persisted veterinary clearance decisions for adoption / surgery (PRR 3.5).

    Replaces the bare ``is_adoptable`` side-effect on the dog profile: the
    attending vet, the decision, and its rationale are recorded as a clearance
    record while the dog flag remains in sync.
    """

    __tablename__ = "medical_clearances"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    authorized_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    # adoption_surgery, pre_adoption_medical, surgical_review, ...
    clearance_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # approved / denied / pending
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
