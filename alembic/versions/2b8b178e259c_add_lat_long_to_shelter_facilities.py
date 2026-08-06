"""add lat long to shelter facilities

Revision ID: 2b8b178e259c
Revises: 4d348cfdbbd1
Create Date: 2026-08-06 12:21:00.796596

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2b8b178e259c'
down_revision: Union[str, None] = '4d348cfdbbd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shelter_facilities",
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
    )
    op.add_column(
        "shelter_facilities",
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shelter_facilities", "longitude")
    op.drop_column("shelter_facilities", "latitude")
