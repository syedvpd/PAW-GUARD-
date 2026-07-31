"""add_oauth_accounts_table

The OAuthAccount ORM model (src/pawguard/modules/auth/models.py) and the
/auth/oauth/* endpoints have existed since the initial auth build, but no
migration ever created the backing table — any code path touching
User.oauth_accounts (OAuth login/link, or simply cascading a user delete)
fails with `relation "oauth_accounts" does not exist`.

Revision ID: a7c9e4f2b8d1
Revises: f1a2b3c4d5e6
Create Date: 2026-07-30 11:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7c9e4f2b8d1"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_accounts",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("provider_email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("picture_url", sa.String(length=512), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_oauth_accounts_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_accounts")),
    )
    op.create_index(
        op.f("ix_oauth_accounts_user_id"), "oauth_accounts", ["user_id"], unique=False
    )
    op.create_index(
        "ix_oauth_accounts_provider",
        "oauth_accounts",
        ["provider", "provider_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_oauth_accounts_provider", table_name="oauth_accounts")
    op.drop_index(op.f("ix_oauth_accounts_user_id"), table_name="oauth_accounts")
    op.drop_table("oauth_accounts")
