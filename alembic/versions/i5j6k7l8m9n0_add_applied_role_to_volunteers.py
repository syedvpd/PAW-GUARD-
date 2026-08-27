"""add applied_role column to volunteer_applications and volunteer_profiles

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-08-27 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i5j6k7l8m9n0"
down_revision: str | None = "h4i5j6k7l8m9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "volunteer_applications",
        sa.Column("applied_role", sa.String(255), nullable=True),
    )
    op.add_column(
        "volunteer_profiles",
        sa.Column("applied_role", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("volunteer_profiles", "applied_role")
    op.drop_column("volunteer_applications", "applied_role")
