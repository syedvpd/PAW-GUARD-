"""add fleet performance indexes for filters, sorting and search

Revision ID: 9f0a1b2c3d4e
Revises: 2b8b178e259c
Create Date: 2026-08-07 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9f0a1b2c3d4e'
down_revision: str | None = '2b8b178e259c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # Partial B-Tree indexes for the most common fleet list filters (status /
    # vehicle_type combined with the default created_at sort).
    op.create_index(
        "idx_vehicles_status_created",
        "vehicles",
        ["status", "created_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_vehicles_type_created",
        "vehicles",
        ["vehicle_type", "created_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
        if_not_exists=True,
    )

    # GIN trigram indexes for ILIKE make/model and plate search.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_make_model_trgm "
        "ON vehicles USING gin (make_model gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_license_plate_trgm "
        "ON vehicles USING gin (license_plate gin_trgm_ops);"
    )

    # Foreign-key lookup indexes (PostgreSQL does not auto-index FKs).
    op.create_index(
        "idx_fleet_maintenances_vehicle_id",
        "fleet_maintenances",
        ["vehicle_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_fuel_logs_vehicle_id",
        "fuel_logs",
        ["vehicle_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_equipment_checkouts_vehicle_id",
        "equipment_checkouts",
        ["assigned_to_vehicle_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_equipment_checkouts_vehicle_id",
        table_name="equipment_checkouts",
        if_exists=True,
    )
    op.drop_index("idx_fuel_logs_vehicle_id", table_name="fuel_logs", if_exists=True)
    op.drop_index(
        "idx_fleet_maintenances_vehicle_id",
        table_name="fleet_maintenances",
        if_exists=True,
    )

    op.execute("DROP INDEX IF EXISTS idx_vehicles_license_plate_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_make_model_trgm;")

    op.drop_index("idx_vehicles_type_created", table_name="vehicles", if_exists=True)
    op.drop_index("idx_vehicles_status_created", table_name="vehicles", if_exists=True)
