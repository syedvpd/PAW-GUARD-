"""add_transfer_kennel_lock_and_vehicle

Revision ID: y2z3a4b5c6d7
Revises: z1a2b3c4d5e6
Create Date: 2026-09-10 00:00:00.000000

Adds `destination_kennel_id`, `vehicle_id`, and `cancel_reason` to
`facility_transfers` so an inter-facility transfer can reserve a specific
destination kennel (soft-locked against other pending transfers), optionally
record the Fleet vehicle used for the handoff, and carry a cancellation
reason. The `IN_TRANSIT` transfer status is a new value on the existing
`status` string column and needs no schema change.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "y2z3a4b5c6d7"
down_revision: Union[str, None] = "z1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "facility_transfers",
        sa.Column("destination_kennel_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "facility_transfers",
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "facility_transfers",
        sa.Column("cancel_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_facility_transfers_destination_kennel_id",
        "facility_transfers",
        ["destination_kennel_id"],
    )
    op.create_index(
        "ix_facility_transfers_vehicle_id",
        "facility_transfers",
        ["vehicle_id"],
    )
    op.create_foreign_key(
        "fk_facility_transfers_destination_kennel_id",
        "facility_transfers",
        "kennels",
        ["destination_kennel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_facility_transfers_vehicle_id",
        "facility_transfers",
        "vehicles",
        ["vehicle_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_facility_transfers_vehicle_id", "facility_transfers", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_facility_transfers_destination_kennel_id", "facility_transfers", type_="foreignkey"
    )
    op.drop_index("ix_facility_transfers_vehicle_id", table_name="facility_transfers")
    op.drop_index("ix_facility_transfers_destination_kennel_id", table_name="facility_transfers")
    op.drop_column("facility_transfers", "cancel_reason")
    op.drop_column("facility_transfers", "vehicle_id")
    op.drop_column("facility_transfers", "destination_kennel_id")
