"""add_transfer_origin_kennel

Revision ID: b3c4d5e6f7a9
Revises: a2b3c4d5e6f8
Create Date: 2026-09-10 00:00:00.000000

Adds `origin_kennel_id` to `facility_transfers` — the dog's kennel at the
sending facility when the transfer was requested, for audit symmetry with
`destination_kennel_id`. Purely additive/nullable; no data backfill needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a9"
down_revision: str | None = "a2b3c4d5e6f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "facility_transfers",
        sa.Column("origin_kennel_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_facility_transfers_origin_kennel_id",
        "facility_transfers",
        ["origin_kennel_id"],
    )
    op.create_foreign_key(
        "fk_facility_transfers_origin_kennel_id",
        "facility_transfers",
        "kennels",
        ["origin_kennel_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_facility_transfers_origin_kennel_id", "facility_transfers", type_="foreignkey"
    )
    op.drop_index("ix_facility_transfers_origin_kennel_id", table_name="facility_transfers")
    op.drop_column("facility_transfers", "origin_kennel_id")
