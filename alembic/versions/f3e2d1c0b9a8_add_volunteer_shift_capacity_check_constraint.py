"""add volunteer shift capacity check constraint

Revision ID: f3e2d1c0b9a8
Revises: d1e2f3a4b5c6
Create Date: 2026-09-16 01:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3e2d1c0b9a8"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    constraint_check = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'ck_volunteer_shifts_capacity_positive'"
        )
    ).scalar()
    if not constraint_check:
        op.create_check_constraint(
            "ck_volunteer_shifts_capacity_positive",
            "volunteer_shifts",
            "capacity > 0",
        )


def downgrade() -> None:
    conn = op.get_bind()
    constraint_check = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'ck_volunteer_shifts_capacity_positive'"
        )
    ).scalar()
    if constraint_check:
        op.drop_constraint(
            "ck_volunteer_shifts_capacity_positive",
            "volunteer_shifts",
            type_="check",
        )
