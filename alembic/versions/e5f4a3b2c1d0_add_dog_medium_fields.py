"""add_dog_medium_fields

Revision ID: e5f4a3b2c1d0
Revises: f8c7d6e5f4a3
Create Date: 2026-08-02 21:40:00.000000

Module 2 (Dog registry) Medium-priority fixes (PRR 3.4):

- M-1: gender + temperament become controlled enums. Legacy free-text rows
  are backfilled onto the canonical values (unrecognized non-null values map
  to 'unknown'); the gender column also gains the index the ORM now declares.
- M-2: new `dog_weight_logs` append-only table backing the weight history.
- M-3: new `breed_classification` column (pure/mix/unknown); existing breeds
  containing mix/cross/indie keywords are backfilled to 'mix', everything
  else keeps the default 'unknown' (staff can correct explicitly).
- M-4: new `section_id` (shelter_sections) and `foster_home_id`
  (foster_profiles) location columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f4a3b2c1d0"
down_revision: str | None = "f8c7d6e5f4a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── M-3: breed classification (defaults to 'unknown' for existing rows) ──
    op.add_column(
        "dog_profiles",
        sa.Column(
            "breed_classification",
            sa.String(length=16),
            server_default="unknown",
            nullable=False,
        ),
    )

    # ── M-4: location fields ─────────────────────────────────────────────────
    op.add_column(
        "dog_profiles",
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "dog_profiles",
        sa.Column("foster_home_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_dog_profiles_section_id_shelter_sections"),
        "dog_profiles",
        "shelter_sections",
        ["section_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_dog_profiles_foster_home_id_foster_profiles"),
        "dog_profiles",
        "foster_profiles",
        ["foster_home_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── M-1: gender index (the ORM model now declares index=True) ───────────
    op.create_index("ix_dog_profiles_gender", "dog_profiles", ["gender"])

    # ── M-2: weight history table ────────────────────────────────────────────
    op.create_table(
        "dog_weight_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "dog_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dog_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "measured_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("weight", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_dog_weight_logs_dog_id", "dog_weight_logs", ["dog_id"])

    # ── M-1: backfill gender onto the controlled set ────────────────────────
    op.execute(
        "UPDATE dog_profiles SET gender = LOWER(gender) "
        "WHERE gender IS DISTINCT FROM LOWER(gender)"
    )
    op.execute(
        "UPDATE dog_profiles SET gender = 'unknown' "
        "WHERE gender NOT IN ('male', 'female', 'unknown')"
    )

    # ── M-1: backfill temperament onto the controlled set ───────────────────
    op.execute(
        "UPDATE dog_profiles SET temperament = 'friendly' "
        "WHERE LOWER(temperament) IN ('calm', 'playful', 'gentle', 'docile', 'sociable')"
    )
    op.execute(
        "UPDATE dog_profiles SET temperament = 'timid_fearful' "
        "WHERE LOWER(temperament) IN ('shy', 'timid', 'fearful', 'nervous', 'scared')"
    )
    op.execute(
        "UPDATE dog_profiles SET temperament = 'high_energy' "
        "WHERE LOWER(temperament) IN ('energetic', 'hyperactive', 'active')"
    )
    op.execute(
        "UPDATE dog_profiles SET temperament = 'aggressive' "
        "WHERE LOWER(temperament) IN ('aggressive', 'reactive')"
    )
    op.execute(
        "UPDATE dog_profiles SET temperament = 'pack_compatible' "
        "WHERE LOWER(temperament) IN ('pack compatible', 'pack-compatible')"
    )
    op.execute(
        "UPDATE dog_profiles SET temperament = 'cat_child_safe' "
        "WHERE LOWER(temperament) IN ('cat safe', 'child safe', 'cat/child safe')"
    )
    op.execute(
        "UPDATE dog_profiles SET temperament = 'unknown' "
        "WHERE temperament IS NOT NULL AND LOWER(temperament) NOT IN "
        "('friendly', 'timid_fearful', 'aggressive', 'high_energy', "
        "'pack_compatible', 'cat_child_safe', 'unknown')"
    )

    # ── M-3: backfill breed classification from free-text breed ─────────────
    op.execute(
        "UPDATE dog_profiles SET breed_classification = 'mix' "
        "WHERE LOWER(breed) LIKE '%mix%' OR LOWER(breed) LIKE '%indie%' "
        "OR LOWER(breed) LIKE '%cross%' OR LOWER(breed) LIKE '%mongrel%'"
    )


def downgrade() -> None:
    op.drop_index("ix_dog_weight_logs_dog_id", table_name="dog_weight_logs")
    op.drop_table("dog_weight_logs")
    op.drop_index("ix_dog_profiles_gender", table_name="dog_profiles")
    op.drop_constraint(
        op.f("fk_dog_profiles_foster_home_id_foster_profiles"),
        "dog_profiles",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_dog_profiles_section_id_shelter_sections"),
        "dog_profiles",
        type_="foreignkey",
    )
    op.drop_column("dog_profiles", "foster_home_id")
    op.drop_column("dog_profiles", "section_id")
    op.drop_column("dog_profiles", "breed_classification")
