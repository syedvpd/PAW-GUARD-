"""add_composite_performance_indexes

Revision ID: e1f2a3b4c5d6
Revises: 3bd5860e2194
Create Date: 2026-08-11 22:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = '3bd5860e2194'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Foster progress logs composite index (placement_id, logged_at DESC)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_foster_progress_logs_placement_logged_at "
        "ON foster_progress_logs (placement_id, logged_at DESC);"
    )

    # 2. Adoption scores composite index (application_id, scored_at DESC)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_adoption_scores_app_scored_at "
        "ON adoption_scores (application_id, scored_at DESC);"
    )

    # 3. Fleet fuel logs composite index (vehicle_id, filled_at DESC)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fuel_logs_vehicle_filled_at "
        "ON fuel_logs (vehicle_id, filled_at DESC);"
    )

    # 4. Dog profiles composite indexes (status, created_at DESC) and (deleted_at, status)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dog_profiles_status_created_at "
        "ON dog_profiles (status, created_at DESC) WHERE deleted_at IS NULL;"
    )

    # 5. Rescue requests composite index (status, created_at DESC)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rescue_requests_status_created_at "
        "ON rescue_requests (status, created_at DESC) WHERE deleted_at IS NULL;"
    )

    # 6. User sessions active index (user_id, is_active, expires_at)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_user_active_expires "
        "ON user_sessions (user_id, is_active, expires_at);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_foster_progress_logs_placement_logged_at;")
    op.execute("DROP INDEX IF EXISTS ix_adoption_scores_app_scored_at;")
    op.execute("DROP INDEX IF EXISTS ix_fuel_logs_vehicle_filled_at;")
    op.execute("DROP INDEX IF EXISTS ix_dog_profiles_status_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_rescue_requests_status_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_user_sessions_user_active_expires;")
