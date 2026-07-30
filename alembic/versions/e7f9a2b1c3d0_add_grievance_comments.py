"""add_grievance_comments_and_status

Revision ID: e7f9a2b1c3d0
Revises: 12b5d8f3f408
Create Date: 2026-07-29 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f9a2b1c3d0"
down_revision: str | None = "12b5d8f3f408"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grievance_comments",
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
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
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["grievance_tickets.id"],
            name=op.f("fk_grievance_comments_ticket_id_grievance_tickets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_grievance_comments_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grievance_comments")),
    )
    op.create_index(
        op.f("ix_grievance_comments_ticket_id"),
        "grievance_comments",
        ["ticket_id"],
        unique=False,
    )

    op.add_column(
        "grievance_tickets",
        sa.Column("reporter_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "grievance_tickets",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "service_feedbacks",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("service_feedbacks", "is_deleted")
    op.drop_column("grievance_tickets", "is_deleted")
    op.drop_column("grievance_tickets", "reporter_email")
    op.drop_index(
        op.f("ix_grievance_comments_ticket_id"), table_name="grievance_comments"
    )
    op.drop_table("grievance_comments")
