"""reconcile p0_3 index predicate and drop kennel single uq

Revision ID: d1e2f3a4b5c6
Revises: c8d9e0f1a2b4
Create Date: 2026-09-15 17:02:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c8d9e0f1a2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. P1-3: Drop uq_dog_profiles_kennel_single so multi-capacity kennels can house multiple dogs
    op.execute("DROP INDEX IF EXISTS uq_dog_profiles_kennel_single")

    # Ensure lookup index on kennel_id exists
    op.execute("CREATE INDEX IF NOT EXISTS ix_dog_profiles_kennel_id ON dog_profiles (kennel_id)")

    # 2. P0-3: Reconcile adoption lock index predicate to match ORM identically:
    # status IN ('home_check', 'approved', 'completed') AND deleted_at IS NULL
    op.execute("DROP INDEX IF EXISTS ix_adoption_applications_dog_lock_states")
    op.execute(
        """
        CREATE UNIQUE INDEX ix_adoption_applications_dog_lock_states
        ON adoption_applications (dog_id)
        WHERE status IN ('home_check', 'approved', 'completed') AND deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_adoption_applications_dog_lock_states")
    op.execute(
        """
        CREATE UNIQUE INDEX ix_adoption_applications_dog_lock_states
        ON adoption_applications (dog_id)
        WHERE status IN ('home_check', 'approved') AND deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dog_profiles_kennel_single
        ON dog_profiles (kennel_id)
        WHERE kennel_id IS NOT NULL AND deleted_at IS NULL
        """
    )
