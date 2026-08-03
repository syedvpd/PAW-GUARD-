"""add thumbnail_object_key to stored_files

Revision ID: b34424e4e94c
Revises: a1b2c3d4e5f6
Create Date: 2026-08-01 22:48:06.451701

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b34424e4e94c'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stored_files",
        sa.Column("thumbnail_object_key", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stored_files", "thumbnail_object_key")
