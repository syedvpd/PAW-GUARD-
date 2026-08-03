"""add_rescue_escalation_protocol

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-02 17:30:00.000000

Adds `escalation_type` (RescueEscalationType: backup_personnel /
vet_transport / law_enforcement / other) and `escalation_notes` to
`rescue_dispatches` for the PRR 3.3 Escalation Protocol - field agents flag
the case when they need back-up personnel, specialized veterinary transport,
or local law enforcement support. Both are optional; existing dispatch rows
get NULL (no escalation requested), so no backfill is needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rescue_dispatches",
        sa.Column("escalation_type", sa.String(length=32), nullable=True),
    )
    op.create_index(
        op.f("ix_rescue_dispatches_escalation_type"),
        "rescue_dispatches",
        ["escalation_type"],
        unique=False,
    )
    op.add_column(
        "rescue_dispatches",
        sa.Column("escalation_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rescue_dispatches", "escalation_notes")
    op.drop_index(
        op.f("ix_rescue_dispatches_escalation_type"),
        table_name="rescue_dispatches",
    )
    op.drop_column("rescue_dispatches", "escalation_type")
