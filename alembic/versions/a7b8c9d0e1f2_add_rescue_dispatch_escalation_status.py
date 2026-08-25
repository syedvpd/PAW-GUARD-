"""add rescue dispatch escalation status lifecycle

Revision ID: a7b8c9d0e1f2
Revises: e39162ae1bfc
Create Date: 2026-08-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "e39162ae1bfc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add escalation_status column to rescue_dispatches.
    # Default 'none' makes this fully backward-compatible -
    # all existing rows are treated as having no active escalation.
    op.add_column(
        "rescue_dispatches",
        sa.Column(
            "escalation_status",
            sa.String(32),
            nullable=False,
            server_default="none",
        ),
    )
    op.create_index(
        "ix_rescue_dispatches_escalation_status",
        "rescue_dispatches",
        ["escalation_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rescue_dispatches_escalation_status",
        table_name="rescue_dispatches",
    )
    op.drop_column("rescue_dispatches", "escalation_status")
