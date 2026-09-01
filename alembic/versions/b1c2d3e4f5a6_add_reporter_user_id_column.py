"""add reporter_user_id column to rescue_requests

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-09-01 11:06:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE rescue_requests ADD COLUMN IF NOT EXISTS reporter_user_id UUID REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rescue_requests_reporter_user_id ON rescue_requests (reporter_user_id)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_rescue_requests_reporter_user_id"
    )
    op.execute(
        "ALTER TABLE rescue_requests DROP COLUMN IF EXISTS reporter_user_id"
    )
