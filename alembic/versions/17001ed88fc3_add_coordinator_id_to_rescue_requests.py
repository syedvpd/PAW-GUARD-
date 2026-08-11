"""add coordinator_id to rescue_requests

Revision ID: 17001ed88fc3
Revises: 4f3c25a44f2e
Create Date: 2026-08-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "17001ed88fc3"
down_revision: Union[str, None] = "4f3c25a44f2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rescue_requests",
        sa.Column(
            "coordinator_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_rescue_requests_coordinator_id", table_name="rescue_requests")
    op.drop_column("rescue_requests", "coordinator_id")
