"""alter_user_profile_picture_url_to_text

Revision ID: c26daf914f40
Revises: 77d202d452ad
Create Date: 2026-08-27 17:38:13.636856

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c26daf914f40'
down_revision: str | None = '77d202d452ad'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns("users")
    for col in columns:
        if col["name"] == "profile_picture_url":
            if not isinstance(col["type"], sa.Text):
                op.alter_column("users", "profile_picture_url", type_=sa.Text(), existing_type=sa.String(length=512), nullable=True)
            break


def downgrade() -> None:
    op.alter_column("users", "profile_picture_url", type_=sa.String(length=512), existing_type=sa.Text(), nullable=True)
