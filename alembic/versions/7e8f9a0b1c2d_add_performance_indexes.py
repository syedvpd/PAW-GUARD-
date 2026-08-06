"""add performance indexes for text search and composite filters

Revision ID: 7e8f9a0b1c2d
Revises: 6da1e36044c4
Create Date: 2026-08-01 23:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7e8f9a0b1c2d'
down_revision: Union[str, None] = '6da1e36044c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pg_trgm extension for ILIKE trigram search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 2. GIN Trigram Indexes for text search
    op.execute("CREATE INDEX IF NOT EXISTS idx_dogs_name_trgm ON dog_profiles USING gin (name gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dogs_breed_trgm ON dog_profiles USING gin (breed gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_inventory_items_name_trgm ON inventory_items USING gin (name gin_trgm_ops);")

    # 3. Composite & Partial B-Tree Indexes for frequent filtering
    op.create_index(
        "idx_dogs_status_shelter_id",
        "dog_profiles",
        ["status", "shelter_facility_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_inventory_items_low_stock",
        "inventory_items",
        ["quantity", "reorder_threshold"],
        postgresql_where=sa.text("deleted_at IS NULL"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_inventory_items_expiry",
        "inventory_items",
        ["expiry_date"],
        postgresql_where=sa.text("deleted_at IS NULL AND expiry_date IS NOT NULL"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_donations_donor_status",
        "donations",
        ["donor_id", "status"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_rescue_requests_status_severity",
        "rescue_requests",
        ["status", "severity"],
        postgresql_where=sa.text("deleted_at IS NULL"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_adoption_apps_status_adopter",
        "adoption_applications",
        ["status", "adopter_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_adoption_apps_status_adopter", table_name="adoption_applications", if_exists=True)
    op.drop_index("idx_rescue_requests_status_severity", table_name="rescue_requests", if_exists=True)
    op.drop_index("idx_donations_donor_status", table_name="donations", if_exists=True)
    op.drop_index("idx_inventory_items_expiry", table_name="inventory_items", if_exists=True)
    op.drop_index("idx_inventory_items_low_stock", table_name="inventory_items", if_exists=True)
    op.drop_index("idx_dogs_status_shelter_id", table_name="dog_profiles", if_exists=True)

    op.execute("DROP INDEX IF EXISTS idx_inventory_items_name_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_dogs_breed_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_dogs_name_trgm;")
