"""add_user_extended_profile_fields

Add extended profile fields to users table for Edit Profile screen:
profile_picture_url, date_of_birth, gender, address_line, city, state,
country, postal_code, push_notifications_enabled.

Revision ID: f9f8e7d6c5b4
Revises: 4e1fa2c99247
Create Date: 2026-08-06 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9f8e7d6c5b4"
down_revision: Union[str, None] = "4e1fa2c99247"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("profile_picture_url", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("address_line", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("city", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("state", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("postal_code", sa.String(length=32), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "push_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "push_notifications_enabled")
    op.drop_column("users", "postal_code")
    op.drop_column("users", "country")
    op.drop_column("users", "state")
    op.drop_column("users", "city")
    op.drop_column("users", "address_line")
    op.drop_column("users", "gender")
    op.drop_column("users", "date_of_birth")
    op.drop_column("users", "profile_picture_url")
