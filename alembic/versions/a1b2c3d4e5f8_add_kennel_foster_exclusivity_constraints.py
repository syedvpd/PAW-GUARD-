"""add kennel and foster exclusive placement DB constraints

PRR 3.6 / 3.8 enforcement at the database level: application-layer checks
were raceable. These partial unique indexes make the exclusivity violation
impossible at the storage layer, even under direct DB writes that bypass
the service layer.

Revision ID: a1b2c3d4e5f8
Revises: f9f8e7d6c5b6
Create Date: 2026-08-10 16:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, None] = "f9f8e7d6c5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PRR 3.6: Fast lookup for dogs in kennels.
    # Kennel capacity (single vs. group housing) is concurrency-checked under
    # SELECT ... FOR UPDATE row locks in shelter service.
    op.create_index(
        "ix_dog_profiles_kennel_id",
        "dog_profiles",
        ["kennel_id"],
        unique=False,
        postgresql_where=sa.text("kennel_id IS NOT NULL AND deleted_at IS NULL"),
    )

    # PRR 3.8: a dog can only have one active foster placement at a time.
    # Soft-closed placements (returned_at set, is_active=false) are excluded
    # so a closed placement does not block a new one.
    op.create_index(
        "uq_foster_placements_active_dog",
        "foster_placements",
        ["dog_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    # PRR 3.7: dog-level adoption approval lock. While any application is
    # in the HOME_CHECK / APPROVED / COMPLETED state for a dog, the dog's is_adoptable
    # flag is locked. Matches the ORM model predicate identically.
    op.create_index(
        "ix_adoption_applications_dog_lock_states",
        "adoption_applications",
        ["dog_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('home_check', 'approved', 'completed') AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_adoption_applications_dog_lock_states", table_name="adoption_applications")
    op.drop_index("uq_foster_placements_active_dog", table_name="foster_placements")
    op.drop_index("ix_dog_profiles_kennel_id", table_name="dog_profiles")
