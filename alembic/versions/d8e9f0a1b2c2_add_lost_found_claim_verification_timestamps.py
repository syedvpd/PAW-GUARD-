"""add_lost_found_claim_verification_timestamps

PRR 3.10: verifiable ownership-claim workflow for lost & found
reunifications. Adds the submission/review timestamps to `report_matches`
so the claim workflow (owner submits proof documents -> staff reviews and
confirms/rejects) carries a full audit trail.

Revision ID: d8e9f0a1b2c2
Revises: d7e8f9a0b1c2
Create Date: 2026-08-03 08:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c2"
down_revision: str | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_matches",
        sa.Column("claim_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "report_matches",
        sa.Column("claim_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("report_matches", "claim_reviewed_at")
    op.drop_column("report_matches", "claim_submitted_at")
