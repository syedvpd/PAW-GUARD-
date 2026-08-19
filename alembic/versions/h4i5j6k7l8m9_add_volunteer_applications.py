"""add volunteer applications table and lifecycle tracking

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-08-19 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "h4i5j6k7l8m9"
down_revision: str | None = "g3h4i5j6k7l8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Create volunteer_applications table
    op.create_table(
        "volunteer_applications",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="submitted", index=True),
        sa.Column("emergency_contact_name", sa.String(255), nullable=False),
        sa.Column("emergency_contact_phone", sa.String(32), nullable=False),
        sa.Column("skills", sa.Text, nullable=True),
        sa.Column("availability", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("medical_conditions", sa.Text, nullable=True),
        sa.Column("animal_handling_experience", sa.Text, nullable=True),
        sa.Column("reviewed_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # Add application_id column to volunteer_profiles
    op.add_column(
        "volunteer_profiles",
        sa.Column("application_id", PG_UUID(as_uuid=True), sa.ForeignKey("volunteer_applications.id", ondelete="SET NULL"), nullable=True, index=True),
    )

    # Migrate existing volunteer profiles with status 'applied' to have applications
    # This ensures backward compatibility
    op.execute("""
        INSERT INTO volunteer_applications (
            id, user_id, status, emergency_contact_name, emergency_contact_phone,
            skills, availability, notes, medical_conditions, animal_handling_experience,
            created_at, updated_at, created_by, updated_by
        )
        SELECT 
            gen_random_uuid(),
            vp.user_id,
            'approved',
            vp.emergency_contact_name,
            vp.emergency_contact_phone,
            vp.skills,
            vp.availability,
            vp.notes,
            vp.medical_conditions,
            vp.animal_handling_experience,
            vp.created_at,
            vp.updated_at,
            vp.created_by,
            vp.updated_by
        FROM volunteer_profiles vp
        WHERE vp.deleted_at IS NULL
        ON CONFLICT (user_id) DO NOTHING
    """)

    # Link existing profiles to their applications
    op.execute("""
        UPDATE volunteer_profiles vp
        SET application_id = va.id
        FROM volunteer_applications va
        WHERE vp.user_id = va.user_id
        AND vp.application_id IS NULL
        AND vp.deleted_at IS NULL
    """)


def downgrade() -> None:
    op.drop_column("volunteer_profiles", "application_id")
    op.drop_table("volunteer_applications")
