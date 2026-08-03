"""add_dog_activity_stream

Revision ID: f8c7d6e5f4a3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-02 20:15:00.000000

Creates the append-only `dog_activity_logs` table backing the dog master
profile's lifecycle activity stream (PRR 3.4 "Historical Activity Stream").
Every lifecycle event - registration, status change, update, deletion, bulk
operations - appends an immutable row, giving each dog a permanent,
audit-ready chronological trail from intake to final resolution.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f8c7d6e5f4a3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dog_activity_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "dog_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dog_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("message", sa.String(512), nullable=False),
        sa.Column("event_metadata", postgresql.JSONB(), nullable=True),
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
    )
    op.create_index(
        "ix_dog_activity_logs_dog_id", "dog_activity_logs", ["dog_id"]
    )
    op.create_index(
        "ix_dog_activity_logs_event_type", "dog_activity_logs", ["event_type"]
    )
    op.create_index(
        "ix_dog_activity_logs_actor_id", "dog_activity_logs", ["actor_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_dog_activity_logs_actor_id", table_name="dog_activity_logs")
    op.drop_index("ix_dog_activity_logs_event_type", table_name="dog_activity_logs")
    op.drop_index("ix_dog_activity_logs_dog_id", table_name="dog_activity_logs")
    op.drop_table("dog_activity_logs")
