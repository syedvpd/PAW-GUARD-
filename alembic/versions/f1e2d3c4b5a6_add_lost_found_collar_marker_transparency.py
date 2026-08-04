"""add_lost_found_collar_marker_transparency

PRR 3.10: Lost & Found scoring transparency and identification fields.

Adds collar/marker fields to LostReport and FoundReport so reporters can
supply identification details. Adds distance_km, temporal_gap_days, and
match_reasons (JSONB) to ReportMatch so the matching algorithm's score-basis
is transparent to staff and adopters.

Revision ID: f1e2d3c4b5a6
Revises: d8e9f0a1b2c2
Create Date: 2026-08-03 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "f1e2d3c4b5a6"
down_revision: str | None = "d8e9f0a1b2c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- LostReport collar/marker fields ---
    op.add_column(
        "lost_reports",
        sa.Column("collar_color", sa.String(64), nullable=True),
    )
    op.add_column(
        "lost_reports",
        sa.Column("collar_description", sa.String(512), nullable=True),
    )
    op.add_column(
        "lost_reports",
        sa.Column("marker_description", sa.Text(), nullable=True),
    )

    # --- FoundReport collar/marker fields ---
    op.add_column(
        "found_reports",
        sa.Column("collar_color", sa.String(64), nullable=True),
    )
    op.add_column(
        "found_reports",
        sa.Column("collar_description", sa.String(512), nullable=True),
    )
    op.add_column(
        "found_reports",
        sa.Column("marker_description", sa.Text(), nullable=True),
    )

    # --- ReportMatch transparency columns ---
    op.add_column(
        "report_matches",
        sa.Column("distance_km", sa.Numeric(8, 2), nullable=True),
    )
    op.add_column(
        "report_matches",
        sa.Column("temporal_gap_days", sa.Numeric(8, 2), nullable=True),
    )
    op.add_column(
        "report_matches",
        sa.Column("match_reasons", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("report_matches", "match_reasons")  # type: ignore[no-untyped-call]
    op.drop_column("report_matches", "temporal_gap_days")
    op.drop_column("report_matches", "distance_km")

    op.drop_column("found_reports", "marker_description")
    op.drop_column("found_reports", "collar_description")
    op.drop_column("found_reports", "collar_color")

    op.drop_column("lost_reports", "marker_description")
    op.drop_column("lost_reports", "collar_description")
    op.drop_column("lost_reports", "collar_color")
