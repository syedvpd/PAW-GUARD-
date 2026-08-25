"""add volunteer shift geofencing fields

Revision ID: c8d9e0f1a2b3
Revises: b2c3d4e5f6g7
Create Date: 2026-08-25 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "b2c3d4e5f6g7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add geofence location columns to volunteer_shifts
    op.add_column(
        "volunteer_shifts",
        sa.Column("location_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "volunteer_shifts",
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "volunteer_shifts",
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "volunteer_shifts",
        sa.Column("allowed_radius_meters", sa.Integer(), nullable=True, server_default="500"),
    )

    # 2. Add check-in / check-out location tracking to shift_attendances
    op.add_column(
        "shift_attendances",
        sa.Column("check_in_lat", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "shift_attendances",
        sa.Column("check_in_lng", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "shift_attendances",
        sa.Column("check_in_distance_meters", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "shift_attendances",
        sa.Column("check_out_lat", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "shift_attendances",
        sa.Column("check_out_lng", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "shift_attendances",
        sa.Column("check_out_distance_meters", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shift_attendances", "check_out_distance_meters")
    op.drop_column("shift_attendances", "check_out_lng")
    op.drop_column("shift_attendances", "check_out_lat")
    op.drop_column("shift_attendances", "check_in_distance_meters")
    op.drop_column("shift_attendances", "check_in_lng")
    op.drop_column("shift_attendances", "check_in_lat")

    op.drop_column("volunteer_shifts", "allowed_radius_meters")
    op.drop_column("volunteer_shifts", "longitude")
    op.drop_column("volunteer_shifts", "latitude")
    op.drop_column("volunteer_shifts", "location_name")
