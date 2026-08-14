"""ORM models for the Emergency Rescue module."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class RescueStatus(StrEnum):
    REPORTED = "reported"
    VERIFIED = "verified"
    DISPATCHED = "dispatched"
    LOCATED = "located"
    RESCUED = "rescued"
    ADMITTED = "admitted"
    REJECTED = "rejected"


class RescuePhysicalCondition(StrEnum):
    """Controlled physical-condition categories per PRR 3.2 intake payload.

    Legacy free-text values (e.g. "Injured", "Critical") are normalised to
    these canonical values by the API schema and the backfill migration, so
    dashboards and reports can group by a stable, bounded set.
    """

    CRITICAL = "critical_life_threatening"  # Critical / Life Threatening
    INJURED = "fractured_injured"  # Fractured / Injured
    SICK = "contagious_sick"  # Contagious Disease / Sick
    MALNOURISHED = "malnourished"
    ABANDONED = "abandoned_stray"  # Abandoned / Stray
    UNKNOWN = "unknown"  # fallback for unmappable legacy values


class RescueSeverity(StrEnum):
    """Operational priority for a rescue case (PRR 3.2 severity prioritization).

    CRITICAL/HIGH cases feed the public urgent-alert banner (PRR 3.1.1) and the
    coordinator dispatch queue; the explicit `is_urgent` flag on the request
    lets coordinators surface a case for community assistance regardless of
    its severity label.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RescueEscalationType(StrEnum):
    """Escalation categories a field agent can request from the app
    (PRR 3.3 Escalation Protocol): back-up personnel, specialized veterinary
    transport, or local law enforcement support.
    """

    BACKUP_PERSONNEL = "backup_personnel"
    VET_TRANSPORT = "vet_transport"
    LAW_ENFORCEMENT = "law_enforcement"
    OTHER = "other"


class RescueFailureReason(StrEnum):
    """Standardized outcome codes for failed rescues (PRR 3.3).

    Field agents must log one of these codes instead of free text so failure
    analytics (Rescue Operational Efficiency Report) can group by a bounded
    set. Legacy free-text values are normalised to these codes by the API
    layer and the backfill migration.
    """

    ANIMAL_FLED = "animal_fled"  # Animal Fled Area
    AREA_INACCESSIBLE = "area_inaccessible"  # Area Inaccessible
    FALSE_REPORT = "false_report"  # False Report
    LOCAL_INTERVENTION_BLOCKED = "local_intervention_blocked"  # Local Intervention Blocked
    OTHER = "other"  # catch-all for unmappable legacy values


class RescueRequest(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "rescue_requests"
    __table_args__ = {"extend_existing": True}


    ticket_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    reporter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reporter_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    reporter_alternate_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reporter_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    location_address: Mapped[str] = mapped_column(Text, nullable=False)
    location_landmark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    animal_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    physical_condition: Mapped[RescuePhysicalCondition] = mapped_column(
        String(64), nullable=False, default=RescuePhysicalCondition.UNKNOWN
    )  # RescuePhysicalCondition enum (PRR 3.2 categories)
    behavioral_indicators: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Media evidence from the public intake wizard (PRR 3.2): up to 5 photos +
    # short video clips, max 50MB combined, enforced by the storage module at
    # upload time. Holds the confirmed object keys returned by the storage
    # presigned-upload flow (same JSONB pattern as RescueReport.photos).
    media_evidence: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # Temporal tracking extras (PRR 3.2): environmental factors (e.g. weather,
    # traffic, hazards) and additional reporter notes captured by the wizard.
    environmental_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporter_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[RescueStatus] = mapped_column(
        String(32), default=RescueStatus.REPORTED, nullable=False, index=True
    )
    # Severity prioritization (PRR 3.2) - reporters self-assess on intake,
    # coordinators refine during verification; CRITICAL/HIGH feed the public
    # urgent-alert banner and the dispatch queue ordering.
    severity: Mapped[RescueSeverity] = mapped_column(
        String(16), default=RescueSeverity.MEDIUM, nullable=False, index=True
    )
    # Explicit urgent flag (PRR 3.1.1): surfaces a case for community
    # assistance / foster placement on the public banner even when its
    # severity label is not CRITICAL/HIGH.
    is_urgent: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    rejection_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Coordinator assigned to oversee this rescue case (PRR 3.2).
    coordinator_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    dispatch: Mapped["RescueDispatch | None"] = relationship(
        back_populates="rescue_request", uselist=False, cascade="all, delete-orphan"
    )
    reports: Mapped[list["RescueReport"]] = relationship(
        back_populates="rescue_request", cascade="all, delete-orphan"
    )


class RescueDispatch(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "rescue_dispatches"
    __table_args__ = {"extend_existing": True}


    rescue_request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rescue_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    assigned_driver_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    ,
        index=True
    )
    vehicle_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # FK-validated vehicle reference (PRR 3.2 resource assignment). The
    # legacy free-text `vehicle_id` column above is kept for back-compat /
    # display; this column is the source of truth for the ACTIVE vehicle
    # assigned to the dispatch and is validated by the service layer.
    assigned_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    equipment_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    located_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rescued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[RescueFailureReason | None] = mapped_column(
        String(255), nullable=True
    )  # RescueFailureReason outcome code (PRR 3.3)
    # Escalation Protocol (PRR 3.3): field agents flag the case when they need
    # back-up personnel, veterinary transport, or law enforcement support.
    escalation_type: Mapped[RescueEscalationType | None] = mapped_column(
        String(32), nullable=True, index=True
    )  # RescueEscalationType request category
    escalation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    rescue_request: Mapped["RescueRequest"] = relationship(back_populates="dispatch")
    # One-or-more assigned agents (PRR 3.2): the legacy `assigned_driver_id`
    # column is mirrored into this association table so a dispatch can carry a
    # full field team and agents can query "my assigned cases".
    agents: Mapped[list["RescueDispatchAgent"]] = relationship(
        back_populates="dispatch", cascade="all, delete-orphan"
    )

    @property
    def status(self) -> Any:
        return self.rescue_request.status

    @property
    def ticket_number(self) -> str:
        return self.rescue_request.ticket_number



class RescueDispatchAgent(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """Association of a rescue dispatch to one of its assigned field agents.

    A dispatch has one or more agents (PRR 3.2 resource assignment). The
    legacy single ``assigned_driver_id`` column on the dispatch is mirrored
    here for back-compat; this table is the source of truth for multi-agent
    teams and the "assigned to me" case filter.
    """

    __tablename__ = "rescue_dispatch_agents"
    __table_args__ = (
        UniqueConstraint(
            "dispatch_id", "agent_id", name="uq_rescue_dispatch_agents_dispatch_agent"
        ),
        {"extend_existing": True},
    )

    dispatch_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rescue_dispatches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)

    dispatch: Mapped["RescueDispatch"] = relationship(back_populates="agents")


class RescueReport(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "rescue_reports"
    __table_args__ = {"extend_existing": True}


    rescue_request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rescue_requests.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photos: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)  # Store up to 5 URLs

    rescue_request: Mapped["RescueRequest"] = relationship(back_populates="reports")
