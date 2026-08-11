"""merge_all_heads

Revision ID: 3bd5860e2194
Revises: 1302f1b61304, 17001ed88fc3, a1b2c3d4e5f7, a1b2c3d4e5f8
Create Date: 2026-08-11 20:09:46.431142

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3bd5860e2194'
down_revision: Union[str, None] = ('1302f1b61304', '17001ed88fc3', 'a1b2c3d4e5f7', 'a1b2c3d4e5f8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
