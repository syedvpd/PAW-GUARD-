"""add lost-pet alert broadcast marker

Revision ID: 4f3c25a44f2e
Revises: a0b1c2d3e4f5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f3c25a44f2e"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lost_reports",
        sa.Column("broadcasted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_lost_reports_broadcasted_at", "lost_reports", ["broadcasted_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_lost_reports_broadcasted_at", table_name="lost_reports")
    op.drop_column("lost_reports", "broadcasted_at")
