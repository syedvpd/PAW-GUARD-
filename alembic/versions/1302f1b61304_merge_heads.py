"""merge_heads

Revision ID: 1302f1b61304
Revises: 4f3c25a44f2e, f9f8e7d6c5b6
Create Date: 2026-08-11 14:51:58.074387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1302f1b61304'
down_revision: Union[str, None] = ('4f3c25a44f2e', 'f9f8e7d6c5b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
