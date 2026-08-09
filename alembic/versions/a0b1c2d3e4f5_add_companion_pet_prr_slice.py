"""add companion pets, safety tags, clinics, appointments and reminders

Revision ID: a0b1c2d3e4f5
Revises: 9f0a1b2c3d4e
Create Date: 2026-08-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "9f0a1b2c3d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "companion_pets",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("species", sa.String(64), server_default="dog", nullable=False),
        sa.Column("breed", sa.String(128), nullable=True),
        sa.Column("sex", sa.String(32), nullable=True),
        sa.Column("birth_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("color", sa.String(128), nullable=True),
        sa.Column("microchip_id", sa.String(64), nullable=True),
        sa.Column("emergency_notes", sa.Text(), nullable=True),
        sa.Column("is_scan_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_common_columns(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companion_pets_owner_id", "companion_pets", ["owner_id"])
    op.create_index(
        "ix_companion_pets_microchip_id", "companion_pets", ["microchip_id"], unique=True
    )
    op.create_index("ix_companion_pets_owner_active", "companion_pets", ["owner_id", "deleted_at"])

    op.create_table(
        "vet_clinics",
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("services", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("is_emergency", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_common_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vet_clinics_name", "vet_clinics", ["name"])
    op.create_index("ix_vet_clinics_is_active", "vet_clinics", ["is_active"])

    op.create_table(
        "vet_clinic_memberships",
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("membership_role", sa.String(32), server_default="staff", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_common_columns(),
        sa.ForeignKeyConstraint(["clinic_id"], ["vet_clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vet_clinic_memberships_clinic_id", "vet_clinic_memberships", ["clinic_id"])
    op.create_index("ix_vet_clinic_memberships_user_id", "vet_clinic_memberships", ["user_id"])
    op.create_index(
        "uq_vet_clinic_memberships_active",
        "vet_clinic_memberships",
        ["clinic_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND is_active IS TRUE"),
    )

    op.create_table(
        "pet_clinic_access",
        sa.Column("pet_id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("granted_by_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_common_columns(),
        sa.ForeignKeyConstraint(["pet_id"], ["companion_pets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["vet_clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pet_clinic_access_pet_id", "pet_clinic_access", ["pet_id"])
    op.create_index("ix_pet_clinic_access_clinic_id", "pet_clinic_access", ["clinic_id"])
    op.create_index(
        "uq_pet_clinic_access_active",
        "pet_clinic_access",
        ["pet_id", "clinic_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND is_active IS TRUE"),
    )

    op.create_table(
        "pet_medical_records",
        sa.Column("pet_id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=True),
        sa.Column("authored_by_id", sa.UUID(), nullable=False),
        sa.Column("stored_file_id", sa.UUID(), nullable=True),
        sa.Column("record_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_common_columns(),
        sa.ForeignKeyConstraint(["pet_id"], ["companion_pets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["vet_clinics.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["authored_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pet_medical_records_pet_id", "pet_medical_records", ["pet_id"])
    op.create_index("ix_pet_medical_records_clinic_id", "pet_medical_records", ["clinic_id"])
    op.create_index(
        "ix_pet_medical_records_stored_file_id", "pet_medical_records", ["stored_file_id"]
    )

    op.create_table(
        "pet_safety_tags",
        sa.Column("pet_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_prefix", sa.String(12), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_count", sa.Integer(), server_default="0", nullable=False),
        *_common_columns(),
        sa.ForeignKeyConstraint(["pet_id"], ["companion_pets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_pet_safety_tags_pet_id", "pet_safety_tags", ["pet_id"])
    op.create_index("ix_pet_safety_tags_token_hash", "pet_safety_tags", ["token_hash"])
    op.create_index("ix_pet_safety_tags_is_active", "pet_safety_tags", ["is_active"])
    op.create_index(
        "uq_pet_safety_tags_active_pet",
        "pet_safety_tags",
        ["pet_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND is_active IS TRUE"),
    )

    op.create_table(
        "pet_reminders",
        sa.Column("pet_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_common_columns(),
        sa.ForeignKeyConstraint(["pet_id"], ["companion_pets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key"),
    )
    op.create_index("ix_pet_reminders_pet_id", "pet_reminders", ["pet_id"])
    op.create_index("ix_pet_reminders_owner_id", "pet_reminders", ["owner_id"])
    op.create_index("ix_pet_reminders_kind", "pet_reminders", ["kind"])
    op.create_index("ix_pet_reminders_due_at", "pet_reminders", ["due_at"])
    op.create_index("ix_pet_reminders_is_active", "pet_reminders", ["is_active"])

    op.create_table(
        "pet_reminder_deliveries",
        sa.Column("reminder_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        *_common_columns()[:3],
        sa.ForeignKeyConstraint(["reminder_id"], ["pet_reminders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pet_reminder_deliveries_reminder_id", "pet_reminder_deliveries", ["reminder_id"]
    )
    op.create_index("ix_pet_reminder_deliveries_user_id", "pet_reminder_deliveries", ["user_id"])
    op.create_index(
        "uq_pet_reminder_deliveries_once",
        "pet_reminder_deliveries",
        ["reminder_id", "user_id", "scheduled_for"],
        unique=True,
    )

    op.create_table(
        "pet_appointments",
        sa.Column("pet_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("vet_id", sa.UUID(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), server_default="requested", nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.String(255), nullable=True),
        *_common_columns(),
        sa.ForeignKeyConstraint(["pet_id"], ["companion_pets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["vet_clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vet_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_pet_appointments_time_order"),
    )
    op.create_index("ix_pet_appointments_pet_id", "pet_appointments", ["pet_id"])
    op.create_index("ix_pet_appointments_owner_id", "pet_appointments", ["owner_id"])
    op.create_index("ix_pet_appointments_clinic_id", "pet_appointments", ["clinic_id"])
    op.create_index("ix_pet_appointments_vet_id", "pet_appointments", ["vet_id"])
    op.create_index("ix_pet_appointments_status", "pet_appointments", ["status"])
    op.create_index(
        "ix_pet_appointments_clinic_time", "pet_appointments", ["clinic_id", "starts_at", "ends_at"]
    )
    op.create_index("ix_pet_appointments_pet_status", "pet_appointments", ["pet_id", "status"])

    # The service pre-check gives friendly errors; this constraint is the
    # concurrency-safe guard against two requests booking the same clinic slot.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        "ALTER TABLE pet_appointments ADD CONSTRAINT ex_pet_appointments_clinic_time "
        "EXCLUDE USING gist (clinic_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) "
        "WHERE (deleted_at IS NULL AND status IN ('requested', 'confirmed'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE pet_appointments DROP CONSTRAINT IF EXISTS ex_pet_appointments_clinic_time"
    )
    for table in (
        "pet_appointments",
        "pet_reminder_deliveries",
        "pet_reminders",
        "pet_safety_tags",
        "pet_medical_records",
        "pet_clinic_access",
        "vet_clinic_memberships",
        "vet_clinics",
        "companion_pets",
    ):
        op.drop_table(table)
