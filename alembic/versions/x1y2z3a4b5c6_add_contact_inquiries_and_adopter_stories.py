"""add contact inquiries and adopter stories

Revision ID: x1y2z3a4b5c6
Revises: w2b3c4d5e6f7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "x1y2z3a4b5c6"
down_revision: Union[str, None] = "w2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update contact_messages table
    op.alter_column("contact_messages", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column("contact_messages", sa.Column("name", sa.String(length=255), nullable=True))
    op.add_column("contact_messages", sa.Column("email", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("contact_messages", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column("contact_messages", sa.Column("category", sa.String(length=128), nullable=False, server_default="general"))
    op.add_column("contact_messages", sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("contact_messages", sa.Column("staff_response", sa.Text(), nullable=True))
    op.add_column("contact_messages", sa.Column("internal_notes", sa.Text(), nullable=True))
    op.add_column("contact_messages", sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contact_messages", sa.Column("responded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("contact_messages", sa.Column("has_consent", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.create_foreign_key(
        "fk_contact_messages_assigned_to_user_id",
        "contact_messages",
        "users",
        ["assigned_to_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_contact_messages_responded_by_user_id",
        "contact_messages",
        "users",
        ["responded_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_contact_messages_email", "contact_messages", ["email"])
    op.create_index("ix_contact_messages_category", "contact_messages", ["category"])
    op.create_index("ix_contact_messages_assigned_to_user_id", "contact_messages", ["assigned_to_user_id"])

    # 2. Update success_stories table
    op.add_column("success_stories", sa.Column("adopter_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("success_stories", sa.Column("has_consent", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("success_stories", sa.Column("rejection_reason", sa.Text(), nullable=True))

    op.create_foreign_key(
        "fk_success_stories_adopter_id",
        "success_stories",
        "users",
        ["adopter_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_success_stories_adopter_id", "success_stories", ["adopter_id"])


def downgrade() -> None:
    op.drop_index("ix_success_stories_adopter_id", table_name="success_stories")
    op.drop_constraint("fk_success_stories_adopter_id", "success_stories", type_="foreignkey")
    op.drop_column("success_stories", "rejection_reason")
    op.drop_column("success_stories", "has_consent")
    op.drop_column("success_stories", "adopter_id")

    op.drop_index("ix_contact_messages_assigned_to_user_id", table_name="contact_messages")
    op.drop_index("ix_contact_messages_category", table_name="contact_messages")
    op.drop_index("ix_contact_messages_email", table_name="contact_messages")
    op.drop_constraint("fk_contact_messages_responded_by_user_id", "contact_messages", type_="foreignkey")
    op.drop_constraint("fk_contact_messages_assigned_to_user_id", "contact_messages", type_="foreignkey")
    op.drop_column("contact_messages", "has_consent")
    op.drop_column("contact_messages", "responded_by_user_id")
    op.drop_column("contact_messages", "responded_at")
    op.drop_column("contact_messages", "internal_notes")
    op.drop_column("contact_messages", "staff_response")
    op.drop_column("contact_messages", "assigned_to_user_id")
    op.drop_column("contact_messages", "category")
    op.drop_column("contact_messages", "phone")
    op.drop_column("contact_messages", "email")
    op.drop_column("contact_messages", "name")
    op.alter_column("contact_messages", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
