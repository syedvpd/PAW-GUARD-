"""add dispatch acceptance timestamps

Revision ID: a8b9c0d1e2f3
Revises: f61eaab29ac9
Create Date: 2026-08-31 17:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, None] = 'f61eaab29ac9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE rescue_dispatches ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE rescue_dispatch_agents ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP WITH TIME ZONE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE rescue_dispatch_agents DROP COLUMN IF EXISTS accepted_at"
    )
    op.execute(
        "ALTER TABLE rescue_dispatches DROP COLUMN IF EXISTS accepted_at"
    )
