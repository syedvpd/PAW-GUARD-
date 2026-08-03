"""add_dog_visual_attributes_and_filters

Revision ID: d6e7f8a9b0c1
Revises: e5f4a3b2c1d0
Create Date: 2026-08-02 22:30:00.000000

Module 2 (Dog registry) Low-priority fixes (PRR 3.4 / PRR 3.1.4):

- L-1: Visual attributes on the dog master profile - ear shape, tail type,
  distinctive markers - so adopters can recognize a dog from its photos.
- L-2: `age_months` numeric column powering the public adoption directory's
  age-range filter (PRR 3.1.4). Existing free-text `estimated_age` rows are
  backfilled where parseable (e.g. "2 years" -> 24, "6 months" -> 6).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "e5f4a3b2c1d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── L-1: visual attributes ──────────────────────────────────────────────
    op.add_column("dog_profiles", sa.Column("ear_shape", sa.String(length=32), nullable=True))
    op.add_column("dog_profiles", sa.Column("tail_type", sa.String(length=32), nullable=True))
    op.add_column("dog_profiles", sa.Column("distinctive_markers", sa.Text(), nullable=True))

    # ── L-2: numeric age for range filtering ────────────────────────────────
    op.add_column(
        "dog_profiles",
        sa.Column("age_months", sa.Integer(), nullable=True),
    )
    op.create_index("ix_dog_profiles_age_months", "dog_profiles", ["age_months"])

    # Backfill age_months from legacy free-text estimated_age where parseable.
    # Integer-valued strings like "2 years" / "2 year" / "6 months" / "1 month".
    op.execute(
        """
        UPDATE dog_profiles
        SET age_months = CAST(REGEXP_REPLACE(estimated_age, '[^0-9]', '', 'g') AS int) * 12
        WHERE estimated_age IS NOT NULL
          AND estimated_age ~* '^[0-9]+[[:space:]]*year'
        """
    )
    op.execute(
        """
        UPDATE dog_profiles
        SET age_months = CAST(REGEXP_REPLACE(estimated_age, '[^0-9]', '', 'g') AS int)
        WHERE estimated_age IS NOT NULL
          AND age_months IS NULL
          AND estimated_age ~* '^[0-9]+[[:space:]]*month'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_dog_profiles_age_months", table_name="dog_profiles")
    op.drop_column("dog_profiles", "age_months")
    op.drop_column("dog_profiles", "distinctive_markers")
    op.drop_column("dog_profiles", "tail_type")
    op.drop_column("dog_profiles", "ear_shape")
