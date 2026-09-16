"""Remediation audit all items: certificates, report_jobs, inventory reference constraint, structured skills, fleet breakdowns, volunteer capacity trigger

Revision ID: f4a1b2c3d4e5
Revises: f3e2d1c0b9a8
Create Date: 2026-09-16 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f4a1b2c3d4e5"
down_revision: Union[str, None] = "f3e2d1c0b9a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    # 1. ITEM 1: digital_certificates table
    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'digital_certificates'")
    ).scalar()
    if not table_exists:
        op.create_table(
            "digital_certificates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cert_id", sa.String(64), unique=True, nullable=False, index=True),
            sa.Column("certificate_type", sa.String(64), nullable=False),
            sa.Column("pet_name", sa.Text(), nullable=True),
            sa.Column("pet_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("recipient_name", sa.Text(), nullable=True),
            sa.Column("clearance_purpose", sa.Text(), nullable=True),
            sa.Column("authorized_by", sa.Text(), nullable=True),
            sa.Column("issue_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="valid"),
            sa.Column(
                "medical_clearance_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("medical_clearances.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_by_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # 2. ITEM 4: InventoryMovement reference integrity constraint
    if is_postgres:
        constraint_check = conn.execute(
            sa.text(
                "SELECT 1 FROM pg_constraint WHERE conname = 'ck_inventory_movement_reference_pair'"
            )
        ).scalar()
        if not constraint_check:
            op.create_check_constraint(
                "ck_inventory_movement_reference_pair",
                "inventory_movements",
                "(reference_id IS NULL AND reference_type IS NULL) OR (reference_id IS NOT NULL AND reference_type IS NOT NULL)",
            )

    # 3. ITEM 5: report_jobs table
    report_jobs_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'report_jobs'")
    ).scalar()
    if not report_jobs_exists:
        op.create_table(
            "report_jobs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("report_type", sa.String(64), nullable=False),
            sa.Column("format", sa.String(16), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
            sa.Column(
                "requester_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("result_object_key", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # 4. ITEM 6: Structured Foster/Volunteer skills to ARRAY(Text)
    if is_postgres:
        # foster_profiles.preferences
        col_type = conn.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns WHERE table_name = 'foster_profiles' AND column_name = 'preferences'"
            )
        ).scalar()
        if col_type == "text" or col_type == "character varying":
            op.execute(
                "ALTER TABLE foster_profiles ALTER COLUMN preferences TYPE text[] USING CASE WHEN preferences IS NULL THEN NULL ELSE string_to_array(trim(preferences), ',') END"
            )

        # volunteer_profiles.skills
        col_type = conn.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns WHERE table_name = 'volunteer_profiles' AND column_name = 'skills'"
            )
        ).scalar()
        if col_type == "text" or col_type == "character varying":
            op.execute(
                "ALTER TABLE volunteer_profiles ALTER COLUMN skills TYPE text[] USING CASE WHEN skills IS NULL THEN NULL ELSE string_to_array(trim(skills), ',') END"
            )

        # volunteer_applications.skills
        col_type = conn.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns WHERE table_name = 'volunteer_applications' AND column_name = 'skills'"
            )
        ).scalar()
        if col_type == "text" or col_type == "character varying":
            op.execute(
                "ALTER TABLE volunteer_applications ALTER COLUMN skills TYPE text[] USING CASE WHEN skills IS NULL THEN NULL ELSE string_to_array(trim(skills), ',') END"
            )

    # 5. ITEM 9e: fleet_breakdown_reports table
    breakdown_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'fleet_breakdown_reports'")
    ).scalar()
    if not breakdown_exists:
        op.create_table(
            "fleet_breakdown_reports",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "vehicle_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "driver_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("breakdown_type", sa.String(64), nullable=False),
            sa.Column("severity", sa.String(32), nullable=False, server_default="moderate"),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("location", sa.Text(), nullable=True),
            sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="reported"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # 6. ITEM 9d: Volunteer Shift Capacity DB Trigger & Function
    if is_postgres:
        op.execute(
            """
            CREATE OR REPLACE FUNCTION check_shift_capacity()
            RETURNS TRIGGER AS $$
            DECLARE
                v_capacity INT;
                v_current_count INT;
            BEGIN
                -- Lock shift row to serialize concurrent claims
                SELECT capacity INTO v_capacity
                FROM volunteer_shifts
                WHERE id = NEW.shift_id
                FOR UPDATE;

                IF v_capacity IS NULL THEN
                    RAISE EXCEPTION 'Shift % does not exist', NEW.shift_id;
                END IF;

                SELECT COUNT(*) INTO v_current_count
                FROM shift_attendances
                WHERE shift_id = NEW.shift_id
                  AND status != 'cancelled';

                IF v_current_count >= v_capacity THEN
                    RAISE EXCEPTION 'Shift % has reached maximum capacity (%)', NEW.shift_id, v_capacity;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_check_shift_capacity ON shift_attendances;")
        op.execute(
            """
            CREATE TRIGGER trg_check_shift_capacity
            BEFORE INSERT ON shift_attendances
            FOR EACH ROW
            EXECUTE FUNCTION check_shift_capacity();
            """
        )


def downgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP TRIGGER IF EXISTS trg_check_shift_capacity ON shift_attendances;")
        op.execute("DROP FUNCTION IF EXISTS check_shift_capacity();")

    op.drop_table("fleet_breakdown_reports")
    op.drop_table("report_jobs")
    if is_postgres:
        op.drop_constraint(
            "ck_inventory_movement_reference_pair",
            "inventory_movements",
            type_="check",
        )
    op.drop_table("digital_certificates")
