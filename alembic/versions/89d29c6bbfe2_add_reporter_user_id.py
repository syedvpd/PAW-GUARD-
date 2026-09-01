"""add_reporter_user_id

Revision ID: 89d29c6bbfe2
Revises: b2c3d4e5f6g7
Create Date: 2026-08-25 15:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "89d29c6bbfe2"
down_revision: Union[str, None] = "b2c3d4e5f6g7"
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
