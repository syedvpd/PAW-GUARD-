"""ensure adoption and foster lock indexes

Revision ID: c8d9e0f1a2b4
Revises: b7c8d9e0f1a2
Create Date: 2026-09-15 16:55:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b4"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Ensure partial unique index on adoption_applications (PRR 3.7 / P0-3)
    # Identical predicate between ORM model and PostgreSQL schema:
    # status IN ('home_check', 'approved', 'completed') AND deleted_at IS NULL
    idx_check_adoption = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_adoption_applications_dog_lock_states'"
        )
    ).scalar()
    if not idx_check_adoption:
        op.create_index(
            "ix_adoption_applications_dog_lock_states",
            "adoption_applications",
            ["dog_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('home_check', 'approved', 'completed') AND deleted_at IS NULL"),
        )

    # 2. Ensure partial unique index on foster_placements active dog
    idx_check_foster = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes WHERE indexname = 'uq_foster_placements_active_dog'"
        )
    ).scalar()
    if not idx_check_foster:
        op.create_index(
            "uq_foster_placements_active_dog",
            "foster_placements",
            ["dog_id"],
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        )


def downgrade() -> None:
    op.drop_index("uq_foster_placements_active_dog", table_name="foster_placements", if_exists=True)
    op.drop_index("ix_adoption_applications_dog_lock_states", table_name="adoption_applications", if_exists=True)
