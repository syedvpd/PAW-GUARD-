"""add_dog_profile_image_urls

Revision ID: a1b2c3d4e5f7
Revises: 84a0660c2de3
Create Date: 2026-08-17 11:00:00.000000

Adds a JSONB column ``image_urls`` to dog_profiles so the public adoption
directory listing can render gallery images directly from external URLs
without requiring a StoredFile row in the storage module. Seed scripts
populate this column with CDN image URLs for adoptable dogs.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'a1b2c3d4e5f7'
down_revision: str | None = '84a0660c2de3'
branch_labels: str | Sequence[str, None] | None = None
depends_on: str | Sequence[str, None] | None = None


def upgrade() -> None:
    op.add_column(
        "dog_profiles",
        sa.Column("image_urls", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dog_profiles", "image_urls")
