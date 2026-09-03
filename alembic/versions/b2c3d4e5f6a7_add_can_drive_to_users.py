"""add can_drive column to users table

Revision ID: b2c3d4e5f6a7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-03 12:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS can_drive BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_can_drive ON users (can_drive)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_can_drive")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS can_drive")
