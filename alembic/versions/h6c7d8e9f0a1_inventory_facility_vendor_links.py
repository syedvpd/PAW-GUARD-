"""inventory: per-facility stock, vendor links, requisition vendor, allow override stock,
add missing audit columns to inventory_item_suppliers

Revision ID: h6c7d8e9f0a1
Revises: g5b6c7d8e9f0
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h6c7d8e9f0a1"
down_revision: Union[str, None] = "g5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_QUANTITY_CHECK = "ck_inventory_items_ck_inventory_items_quantity_non_negative"


def upgrade() -> None:
    op.drop_constraint(op.f(_QUANTITY_CHECK), "inventory_items", type_="check")

    op.add_column(
        "inventory_items",
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_items_facility_id_shelter_facilities",
        "inventory_items",
        "shelter_facilities",
        ["facility_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_inventory_items_facility_id", "inventory_items", ["facility_id"])
    op.drop_constraint("uq_inventory_items_name", "inventory_items", type_="unique")
    op.create_index(
        "uq_inventory_items_name_facility",
        "inventory_items",
        ["name", "facility_id"],
        unique=True,
        postgresql_where=sa.text("facility_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "uq_inventory_items_name_unassigned",
        "inventory_items",
        ["name"],
        unique=True,
        postgresql_where=sa.text("facility_id IS NULL AND deleted_at IS NULL"),
    )

    op.add_column(
        "requisition_orders",
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_requisition_orders_supplier_id_suppliers",
        "requisition_orders",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_requisition_orders_supplier_id", "requisition_orders", ["supplier_id"])

    for column in ("created_by", "updated_by"):
        op.execute(
            f"ALTER TABLE inventory_item_suppliers ADD COLUMN IF NOT EXISTS {column} UUID "
            "REFERENCES users(id) ON DELETE SET NULL"
        )
        op.create_index(
            f"ix_inventory_item_suppliers_{column}",
            "inventory_item_suppliers",
            [column],
            if_not_exists=True,
        )

    op.create_index(
        "uq_inventory_item_suppliers_item_supplier",
        "inventory_item_suppliers",
        ["item_id", "supplier_id"],
        unique=True,
    )
    op.create_index(
        "uq_inventory_item_suppliers_one_preferred",
        "inventory_item_suppliers",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("is_preferred"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_inventory_item_suppliers_one_preferred", table_name="inventory_item_suppliers"
    )
    op.drop_index(
        "uq_inventory_item_suppliers_item_supplier", table_name="inventory_item_suppliers"
    )

    op.drop_index("ix_requisition_orders_supplier_id", table_name="requisition_orders")
    op.drop_constraint(
        "fk_requisition_orders_supplier_id_suppliers", "requisition_orders", type_="foreignkey"
    )
    op.drop_column("requisition_orders", "supplier_id")

    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT COUNT(*) FROM (SELECT name FROM inventory_items "
                "GROUP BY name HAVING COUNT(*) > 1) d"
            )
        )
        .scalar()
    )
    if duplicates:
        raise RuntimeError(
            f"Refusing to downgrade: {duplicates} item name(s) exist in more than one facility. "
            "Merge or rename them before restoring the global unique name constraint."
        )
    op.drop_index("uq_inventory_items_name_unassigned", table_name="inventory_items")
    op.drop_index("uq_inventory_items_name_facility", table_name="inventory_items")
    op.create_unique_constraint("uq_inventory_items_name", "inventory_items", ["name"])
    op.drop_index("ix_inventory_items_facility_id", table_name="inventory_items")
    op.drop_constraint(
        "fk_inventory_items_facility_id_shelter_facilities", "inventory_items", type_="foreignkey"
    )
    op.drop_column("inventory_items", "facility_id")

    op.execute(
        f"ALTER TABLE inventory_items ADD CONSTRAINT {_QUANTITY_CHECK} "
        "CHECK (quantity >= 0) NOT VALID"
    )
