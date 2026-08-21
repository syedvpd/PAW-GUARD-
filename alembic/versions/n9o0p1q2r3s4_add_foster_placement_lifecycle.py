"""add foster placement lifecycle fields

Revision ID: n9o0p1q2r3s4
Revises: m8n9p0q1r2s3
Create Date: 2026-08-21 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n9o0p1q2r3s4"
down_revision: Union[str, None] = "m8n9p0q1r2s3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "foster_profiles",
        sa.Column("background_check_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "foster_profiles",
        sa.Column("reference_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "foster_placements",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.add_column(
        "foster_placements",
        sa.Column("adoption_application_id", sa.UUID(), nullable=True),
    )
    op.create_index("ix_foster_placements_status", "foster_placements", ["status"])
    op.create_unique_constraint(
        "uq_foster_placements_adoption_application_id",
        "foster_placements",
        ["adoption_application_id"],
    )
    op.create_foreign_key(
        "fk_foster_placements_adoption_application_id",
        "foster_placements",
        "adoption_applications",
        ["adoption_application_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_foster_placements_adoption_application_id", "foster_placements", type_="foreignkey")
    op.drop_constraint("uq_foster_placements_adoption_application_id", "foster_placements", type_="unique")
    op.drop_index("ix_foster_placements_status", table_name="foster_placements")
    op.drop_column("foster_placements", "adoption_application_id")
    op.drop_column("foster_placements", "status")
    op.drop_column("foster_profiles", "reference_notes")
    op.drop_column("foster_profiles", "background_check_notes")
