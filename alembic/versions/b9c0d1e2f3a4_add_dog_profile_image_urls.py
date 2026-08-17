"""add_dog_profile_image_urls

Revision ID: b9c0d1e2f3a4
Revises: 84a0660c2de3
Create Date: 2026-08-17 11:00:00.000000

Adds a JSONB column ``image_urls`` to dog_profiles so the public adoption
directory listing can render gallery images directly from external URLs
without requiring a StoredFile row in the storage module. Seed scripts
populate this column with CDN image URLs for adoptable dogs.
"""
from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'b9c0d1e2f3a4'
down_revision: Union[str, None] = '84a0660c2de3'
branch_labels: Union[str, Sequence[str, None], None] = None
depends_on: Union[str, Sequence[str, None], None] = None


def upgrade() -> None:
    op.add_column(
        "dog_profiles",
        sa.Column("image_urls", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dog_profiles", "image_urls")
