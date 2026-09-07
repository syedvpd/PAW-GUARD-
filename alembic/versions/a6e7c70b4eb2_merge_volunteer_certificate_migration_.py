"""merge volunteer certificate migration branch

Revision ID: a6e7c70b4eb2
Revises: c3d4e5f6a7b8, v1a2b3c4d5e6
Create Date: 2026-09-07 10:15:06.540338

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6e7c70b4eb2"
down_revision: Union[str, None] = ("c3d4e5f6a7b8", "v1a2b3c4d5e6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
