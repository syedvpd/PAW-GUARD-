"""add_reporter_user_id_to_rescue_requests

Revision ID: 89d29c6bbfe2
Revises: c8d9e0f1a2b3
Create Date: 2026-08-25 15:22:42.583061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision: str = '89d29c6bbfe2'
down_revision: Union[str, None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'rescue_requests',
        sa.Column('reporter_user_id', PG_UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    )


def downgrade() -> None:
    op.drop_column('rescue_requests', 'reporter_user_id')