"""add interview call fields and home inspection type

Revision ID: q3r4s5t6u7v8
Revises: i5j6k7l8m9n0
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'q3r4s5t6u7v8'
down_revision: Union[str, None] = 'i5j6k7l8m9n0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('adoption_applications', sa.Column('home_inspection_type', sa.String(length=16), nullable=True))
    op.add_column('adoption_applications', sa.Column('interview_scheduled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('adoption_applications', sa.Column('interview_notes', sa.Text(), nullable=True))
    op.add_column('adoption_applications', sa.Column('interview_completed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('adoption_applications', 'interview_completed_at')
    op.drop_column('adoption_applications', 'interview_notes')
    op.drop_column('adoption_applications', 'interview_scheduled_at')
    op.drop_column('adoption_applications', 'home_inspection_type')
