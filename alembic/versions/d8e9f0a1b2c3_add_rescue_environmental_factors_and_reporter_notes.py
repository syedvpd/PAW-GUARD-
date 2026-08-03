"""add_rescue_environmental_factors_and_reporter_notes

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-02 17:00:00.000000

Adds `environmental_factors` and `reporter_notes` (PRR 3.2 Temporal Tracking
extras captured by the intake wizard) to `rescue_requests`. Both are optional
Text columns - no backfill needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rescue_requests",
        sa.Column("environmental_factors", sa.Text(), nullable=True),
    )
    op.add_column(
        "rescue_requests",
        sa.Column("reporter_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rescue_requests", "reporter_notes")
    op.drop_column("rescue_requests", "environmental_factors")
