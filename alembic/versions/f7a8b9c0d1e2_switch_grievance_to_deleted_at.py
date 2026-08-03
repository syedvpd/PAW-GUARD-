"""switch_grievance_to_deleted_at

Revision ID: f7a8b9c0d1e2
Revises: f5a6b7c8d9e0
Create Date: 2026-08-02 19:10:00.000000

Migrates the grievance module's soft-delete flag from the boolean
`is_deleted` column to the platform-standard `deleted_at` timestamp
(SoftDeleteMixin), matching every other module in the backend.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "grievance_tickets",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "service_feedbacks",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        "UPDATE grievance_tickets SET deleted_at = now() WHERE is_deleted = true"
    )
    op.execute(
        "UPDATE service_feedbacks SET deleted_at = now() WHERE is_deleted = true"
    )

    op.drop_column("grievance_tickets", "is_deleted")
    op.drop_column("service_feedbacks", "is_deleted")


def downgrade() -> None:
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

    op.execute(
        "UPDATE grievance_tickets SET is_deleted = true WHERE deleted_at IS NOT NULL"
    )
    op.execute(
        "UPDATE service_feedbacks SET is_deleted = true WHERE deleted_at IS NOT NULL"
    )

    op.drop_column("grievance_tickets", "deleted_at")
    op.drop_column("service_feedbacks", "deleted_at")
