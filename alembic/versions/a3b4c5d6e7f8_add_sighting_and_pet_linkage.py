"""add_sighting_and_pet_linkage

Revision ID: a3b4c5d6e7f8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-13 21:30:00.000000

"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a3b4c5d6e7f8'
down_revision: str | None = 'a2b3c4d5e6f7'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add original_dog_id and adoption_application_id to companion_pets
    op.add_column(
        'companion_pets',
        sa.Column('original_dog_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dogs.id', ondelete='SET NULL'), nullable=True)
    )
    op.add_column(
        'companion_pets',
        sa.Column('adoption_application_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('adoption_applications.id', ondelete='SET NULL'), nullable=True)
    )
    op.create_index('ix_companion_pets_original_dog_id', 'companion_pets', ['original_dog_id'])
    op.create_index('ix_companion_pets_adoption_application_id', 'companion_pets', ['adoption_application_id'])

    # 2. Add companion_pet_id to lost_reports
    op.add_column(
        'lost_reports',
        sa.Column('companion_pet_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companion_pets.id', ondelete='SET NULL'), nullable=True)
    )
    op.create_index('ix_lost_reports_companion_pet_id', 'lost_reports', ['companion_pet_id'])

    # 3. Create pet_sightings table
    op.create_table(
        'pet_sightings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('pet_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companion_pets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('lost_report_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('lost_reports.id', ondelete='SET NULL'), nullable=True),
        sa.Column('finder_name', sa.String(255), nullable=False),
        sa.Column('finder_phone', sa.String(32), nullable=False),
        sa.Column('finder_address', sa.Text(), nullable=True),
        sa.Column('latitude', sa.Numeric(9, 6), nullable=True),
        sa.Column('longitude', sa.Numeric(9, 6), nullable=True),
        sa.Column('location_address', sa.Text(), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_pet_sightings_pet_id', 'pet_sightings', ['pet_id'])
    op.create_index('ix_pet_sightings_lost_report_id', 'pet_sightings', ['lost_report_id'])


def downgrade() -> None:
    op.drop_table('pet_sightings')
    op.drop_index('ix_lost_reports_companion_pet_id', 'lost_reports')
    op.drop_column('lost_reports', 'companion_pet_id')
    op.drop_index('ix_companion_pets_adoption_application_id', 'companion_pets')
    op.drop_index('ix_companion_pets_original_dog_id', 'companion_pets')
    op.drop_column('companion_pets', 'adoption_application_id')
    op.drop_column('companion_pets', 'original_dog_id')
