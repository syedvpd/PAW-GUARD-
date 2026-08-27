"""add interview call fields and home inspection type

Revision ID: q3r4s5t6u7v8
Revises: i5j6k7l8m9n0
Create Date: 2026-08-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "q3r4s5t6u7v8"
down_revision: str | None = "i5j6k7l8m9n0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("adoption_applications")}

    if "home_inspection_type" not in existing_cols:
        op.add_column(
            "adoption_applications",
            sa.Column("home_inspection_type", sa.String(length=16), nullable=True),
        )
    if "interview_scheduled_at" not in existing_cols:
        op.add_column(
            "adoption_applications",
            sa.Column("interview_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "interview_notes" not in existing_cols:
        op.add_column(
            "adoption_applications", sa.Column("interview_notes", sa.Text(), nullable=True)
        )
    if "interview_completed_at" not in existing_cols:
        op.add_column(
            "adoption_applications",
            sa.Column("interview_completed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("adoption_applications")}

    if "interview_completed_at" in existing_cols:
        op.drop_column("adoption_applications", "interview_completed_at")
    if "interview_notes" in existing_cols:
        op.drop_column("adoption_applications", "interview_notes")
    if "interview_scheduled_at" in existing_cols:
        op.drop_column("adoption_applications", "interview_scheduled_at")
    if "home_inspection_type" in existing_cols:
        op.drop_column("adoption_applications", "home_inspection_type")
