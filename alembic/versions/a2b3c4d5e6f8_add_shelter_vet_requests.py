"""add shelter vet requests

Revision ID: a2b3c4d5e6f8
Revises: x1y2z3a4b5c6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a2b3c4d5e6f8"
down_revision: Union[str, None] = "y2z3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create shelter_vet_requests table
    op.create_table(
        "shelter_vet_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dog_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dog_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shelter_facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shelter_facilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("urgency", sa.String(length=32), nullable=False, server_default="routine"),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        # TimestampMixin columns
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # AuditMixin columns
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Create indexes for common query patterns
    op.create_index(
        "ix_shelter_vet_requests_dog_id",
        "shelter_vet_requests",
        ["dog_id"],
    )
    op.create_index(
        "ix_shelter_vet_requests_shelter_facility_id",
        "shelter_vet_requests",
        ["shelter_facility_id"],
    )
    op.create_index(
        "ix_shelter_vet_requests_requested_by_id",
        "shelter_vet_requests",
        ["requested_by_id"],
    )
    op.create_index(
        "ix_shelter_vet_requests_vet_id",
        "shelter_vet_requests",
        ["vet_id"],
    )
    op.create_index(
        "ix_shelter_vet_requests_status",
        "shelter_vet_requests",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_shelter_vet_requests_status", table_name="shelter_vet_requests")
    op.drop_index("ix_shelter_vet_requests_vet_id", table_name="shelter_vet_requests")
    op.drop_index("ix_shelter_vet_requests_requested_by_id", table_name="shelter_vet_requests")
    op.drop_index("ix_shelter_vet_requests_shelter_facility_id", table_name="shelter_vet_requests")
    op.drop_index("ix_shelter_vet_requests_dog_id", table_name="shelter_vet_requests")
    op.drop_table("shelter_vet_requests")
