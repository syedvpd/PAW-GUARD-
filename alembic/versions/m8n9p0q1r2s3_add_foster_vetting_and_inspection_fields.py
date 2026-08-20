"""add foster vetting and inspection fields

Revision ID: m8n9p0q1r2s3
Revises: k7l8m9n0p1q2
Create Date: 2026-08-20 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'm8n9p0q1r2s3'
down_revision: Union[str, None] = 'k7l8m9n0p1q2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('foster_profiles', sa.Column('background_check_passed', sa.Boolean(), nullable=True))
    op.add_column('foster_profiles', sa.Column('references_checked', sa.Boolean(), nullable=True))
    op.add_column('foster_profiles', sa.Column('vetting_notes', sa.Text(), nullable=True))
    op.add_column('foster_profiles', sa.Column('vetted_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column('foster_profiles', sa.Column('home_inspection_passed', sa.Boolean(), nullable=True))
    op.add_column('foster_profiles', sa.Column('home_inspection_notes', sa.Text(), nullable=True))
    op.add_column('foster_profiles', sa.Column('home_inspection_address', sa.Text(), nullable=True))
    op.add_column('foster_profiles', sa.Column('inspected_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('foster_profiles', 'inspected_at')
    op.drop_column('foster_profiles', 'home_inspection_address')
    op.drop_column('foster_profiles', 'home_inspection_notes')
    op.drop_column('foster_profiles', 'home_inspection_passed')

    op.drop_column('foster_profiles', 'vetted_at')
    op.drop_column('foster_profiles', 'vetting_notes')
    op.drop_column('foster_profiles', 'references_checked')
    op.drop_column('foster_profiles', 'background_check_passed')
