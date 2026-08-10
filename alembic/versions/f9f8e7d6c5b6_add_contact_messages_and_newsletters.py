"""add registered-user contact messages and newsletter subscriptions

Revision ID: f9f8e7d6c5b6
Revises: f9f8e7d6c5b5
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f9f8e7d6c5b6"
down_revision: Union[str, None] = "f9f8e7d6c5b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contact_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_contact_messages_user_id", "contact_messages", ["user_id"])
    op.create_index("ix_contact_messages_status", "contact_messages", ["status"])

    op.create_table(
        "newsletter_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_newsletter_subscriptions_user_id", "newsletter_subscriptions", ["user_id"])
    op.create_index("ix_newsletter_subscriptions_is_active", "newsletter_subscriptions", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_newsletter_subscriptions_is_active", table_name="newsletter_subscriptions")
    op.drop_index("ix_newsletter_subscriptions_user_id", table_name="newsletter_subscriptions")
    op.drop_table("newsletter_subscriptions")
    op.drop_index("ix_contact_messages_status", table_name="contact_messages")
    op.drop_index("ix_contact_messages_user_id", table_name="contact_messages")
    op.drop_table("contact_messages")
