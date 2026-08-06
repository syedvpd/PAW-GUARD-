"""merge all migration branches

Revision ID: 4d348cfdbbd1
Revises: 7e8f9a0b1c2d, f1e2d3c4b5a6, f9f8e7d6c5b5
Create Date: 2026-08-06 11:44:13.557612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4d348cfdbbd1'
down_revision: Union[str, None] = ('7e8f9a0b1c2d', 'f1e2d3c4b5a6', 'f9f8e7d6c5b5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
