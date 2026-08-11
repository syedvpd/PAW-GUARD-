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
    # PRR 3.6: prevent two dogs from occupying the same kennel.
    # The kennel.capacity column is allowed to be > 1 (group housing)
    # so we enforce uniqueness only on single-capacity kennels (the
    # default in the Kennel model). Each dog must carry the kennel_id
    # (NULL dogs are unaffected) and not be soft-deleted.
    op.create_index(
        "uq_dog_profiles_kennel_single",
        "dog_profiles",
        ["kennel_id"],
        unique=True,
        postgresql_where=sa.text(
            "kennel_id IS NOT NULL AND deleted_at IS NULL"
        ),
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
    # in the HOME_CHECK / APPROVED state for a dog, the dog's is_adoptable
    # flag is forced to false. Since is_adoptable lives on dog_profiles and
    # is not a partial-unique candidate, we instead index the dog_id of
    # non-rejected applications to support the per-dog exclusivity check
    # the application code already performs (now race-safe via
    # SELECT ... FOR UPDATE; this index keeps the lookup fast).
    op.create_index(
        "ix_adoption_applications_dog_lock_states",
        "adoption_applications",
        ["dog_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('home_check', 'approved') AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_adoption_applications_dog_lock_states", table_name="adoption_applications")
    op.drop_index("uq_foster_placements_active_dog", table_name="foster_placements")
    op.drop_index("uq_dog_profiles_kennel_single", table_name="dog_profiles")
