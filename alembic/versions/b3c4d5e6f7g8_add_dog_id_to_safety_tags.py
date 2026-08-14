"""add dog_id to pet_safety_tags and backfill from companion_pets

Revision ID: b3c4d5e6f7g8
Revises: c1d2e3f4a5b6
Create Date: 2026-08-14 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7g8"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add dog_id column
    op.add_column(
        "pet_safety_tags",
        sa.Column(
            "dog_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dog_profiles.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_pet_safety_tags_dog_id", "pet_safety_tags", ["dog_id"])

    # 2. Backfill dog_id from companion_pets.original_dog_id
    op.execute(
        """
        UPDATE pet_safety_tags pst
        SET dog_id = cp.original_dog_id
        FROM companion_pets cp
        WHERE pst.pet_id = cp.id
          AND cp.original_dog_id IS NOT NULL
          AND pst.dog_id IS NULL;
        """
    )

    # 3. Make pet_id nullable
    op.alter_column(
        "pet_safety_tags",
        "pet_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # 4. Update active tag partial unique constraint to dog_id
    op.execute("DROP INDEX IF EXISTS uq_pet_safety_tags_active_pet;")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_pet_safety_tags_active_dog
        ON pet_safety_tags (dog_id)
        WHERE deleted_at IS NULL AND is_active IS TRUE AND dog_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_pet_safety_tags_active_dog;")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_pet_safety_tags_active_pet
        ON pet_safety_tags (pet_id)
        WHERE deleted_at IS NULL AND is_active IS TRUE AND pet_id IS NOT NULL;
        """
    )
    op.drop_index("ix_pet_safety_tags_dog_id", table_name="pet_safety_tags")
    op.drop_column("pet_safety_tags", "dog_id")
