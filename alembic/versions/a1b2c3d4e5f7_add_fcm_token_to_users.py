"""Add FCM token to users for push notifications.

Revision ID: a1b2c3d4e5f7
Revises: f9f8e7d6c5b6
Create Date: 2026-08-11
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f7"
down_revision = "f9f8e7d6c5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("fcm_token", sa.String(length=512), nullable=True),
    )
    op.create_index(
        "ix_users_fcm_token",
        "users",
        ["fcm_token"],
        unique=False,
        postgresql_where=sa.text("fcm_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_fcm_token", table_name="users")
    op.drop_column("users", "fcm_token")
