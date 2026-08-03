"""add_rescue_severity_and_urgent

Revision ID: b6c7d8e9f0a3
Revises: a4b5c6d7e8f9
Create Date: 2026-08-02 16:00:00.000000

Adds `severity` (PRR 3.2 severity prioritization) and `is_urgent` (PRR 3.1.1
urgent-alert banner flag) to `rescue_requests`. Existing rows backfill to
`medium` / `false` so the columns are NOT NULL with no data migration drama.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6c7d8e9f0a3"
down_revision: str | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rescue_requests",
        sa.Column(
            "severity",
            sa.String(length=16),
            server_default="medium",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_rescue_requests_severity"),
        "rescue_requests",
        ["severity"],
        unique=False,
    )
    op.add_column(
        "rescue_requests",
        sa.Column(
            "is_urgent",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_rescue_requests_is_urgent"),
        "rescue_requests",
        ["is_urgent"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rescue_requests_is_urgent"), table_name="rescue_requests")
    op.drop_column("rescue_requests", "is_urgent")
    op.drop_index(op.f("ix_rescue_requests_severity"), table_name="rescue_requests")
    op.drop_column("rescue_requests", "severity")
