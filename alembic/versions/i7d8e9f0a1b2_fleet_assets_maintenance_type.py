"""fleet: equipment asset register, maintenance type, missing audit columns on
fleet_breakdown_reports

Revision ID: i7d8e9f0a1b2
Revises: h6c7d8e9f0a1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "i7d8e9f0a1b2"
down_revision: str | None = "h6c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equipment_assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, server_default="other"),
        sa.Column("serial_number", sa.String(128), nullable=True),
        sa.Column("condition", sa.String(32), nullable=False, server_default="good"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
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
        sa.UniqueConstraint("serial_number", name="uq_equipment_assets_serial_number"),
    )
    for column in ("created_at", "updated_at", "created_by", "updated_by"):
        op.create_index(f"ix_equipment_assets_{column}", "equipment_assets", [column])

    op.add_column(
        "equipment_checkouts",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_equipment_checkouts_asset_id_equipment_assets",
        "equipment_checkouts",
        "equipment_assets",
        ["asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_equipment_checkouts_asset_id", "equipment_checkouts", ["asset_id"])
    op.create_index(
        "uq_equipment_checkouts_asset_outstanding",
        "equipment_checkouts",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("asset_id IS NOT NULL AND returned_at IS NULL"),
    )

    op.add_column(
        "fleet_maintenances",
        sa.Column("maintenance_type", sa.String(32), nullable=False, server_default="service"),
    )

    for column in ("created_by", "updated_by"):
        op.execute(
            f"ALTER TABLE fleet_breakdown_reports ADD COLUMN IF NOT EXISTS {column} UUID "
            "REFERENCES users(id) ON DELETE SET NULL"
        )
        op.create_index(
            f"ix_fleet_breakdown_reports_{column}",
            "fleet_breakdown_reports",
            [column],
            if_not_exists=True,
        )


def downgrade() -> None:
    op.drop_column("fleet_maintenances", "maintenance_type")
    op.drop_index("uq_equipment_checkouts_asset_outstanding", table_name="equipment_checkouts")
    op.drop_index("ix_equipment_checkouts_asset_id", table_name="equipment_checkouts")
    op.drop_constraint(
        "fk_equipment_checkouts_asset_id_equipment_assets",
        "equipment_checkouts",
        type_="foreignkey",
    )
    op.drop_column("equipment_checkouts", "asset_id")
    op.drop_table("equipment_assets")
