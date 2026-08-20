"""add repository wide performance indexes

Revision ID: k7l8m9n0p1q2
Revises: j6k7l8m9n0p1
Create Date: 2026-08-20 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'k7l8m9n0p1q2'
down_revision: Union[str, None] = 'j6k7l8m9n0p1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'idx_dogs_perf_status_deleted',
        'dog_profiles',
        ['deleted_at', 'is_adoptable', 'status'],
        unique=False,
    )
    op.create_index(
        'idx_rescue_perf_status_severity',
        'rescue_requests',
        ['deleted_at', 'status', 'severity'],
        unique=False,
    )
    op.create_index(
        'idx_adoptions_perf_status_adopter',
        'adoption_applications',
        ['deleted_at', 'status', 'adopter_id'],
        unique=False,
    )
    op.create_index(
        'idx_companion_pets_perf_owner_species',
        'companion_pets',
        ['deleted_at', 'owner_id', 'species'],
        unique=False,
    )
    op.create_index(
        'idx_notifications_perf_user_read',
        'notifications',
        ['user_id', 'is_read', 'created_at'],
        unique=False,
    )
    op.create_index(
        'idx_audit_logs_perf_user_created',
        'auth_audit_logs',
        ['user_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'idx_shelter_facilities_perf_deleted',
        'shelter_facilities',
        ['deleted_at', 'status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_shelter_facilities_perf_deleted', table_name='shelter_facilities')
    op.drop_index('idx_audit_logs_perf_user_created', table_name='auth_audit_logs')
    op.drop_index('idx_notifications_perf_user_read', table_name='notifications')
    op.drop_index('idx_companion_pets_perf_owner_species', table_name='companion_pets')
    op.drop_index('idx_adoptions_perf_status_adopter', table_name='adoption_applications')
    op.drop_index('idx_rescue_perf_status_severity', table_name='rescue_requests')
    op.drop_index('idx_dogs_perf_status_deleted', table_name='dog_profiles')
