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
    op.add_column(
        'rescue_dispatches',
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'rescue_dispatch_agents',
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('rescue_dispatch_agents', 'accepted_at')
    op.drop_column('rescue_dispatches', 'accepted_at')
