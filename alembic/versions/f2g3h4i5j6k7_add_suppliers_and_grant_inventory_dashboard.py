"""add suppliers table, inventory_item_suppliers, grant dashboard:inventory

Revision ID: f2g3h4i5j6k7
Revises: e1f2g3h4i5j6
Create Date: 2026-08-19 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "f2g3h4i5j6k7"
down_revision: str | None = "e1f2g3h4i5j6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ── Suppliers table ───────────────────────────────────────────────
    op.create_table(
        "suppliers",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("contact_person", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("gst_number", sa.String(64), nullable=True),
        sa.Column("pan_number", sa.String(20), nullable=True),
        sa.Column("bank_details", sa.Text, nullable=True),
        sa.Column("payment_terms", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # ── Inventory item ↔ Supplier link table ──────────────────────────
    op.create_table(
        "inventory_item_suppliers",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("item_id", PG_UUID(as_uuid=True), sa.ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("supplier_id", PG_UUID(as_uuid=True), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("unit_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("lead_time_days", sa.Integer, nullable=True),
        sa.Column("is_preferred", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── Grant dashboard:inventory to inventory_manager role ───────────
    op.execute(
        sa.text(
            "INSERT INTO permissions (id, code, description, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :code, :desc, now(), now()) "
            "ON CONFLICT (code) DO NOTHING"
        ).bindparams(code="dashboard:inventory", desc="Access the inventory dashboard summary")
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id "
            "FROM roles r, permissions p "
            "WHERE r.name = 'inventory_manager' AND p.code = 'dashboard:inventory' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM role_permissions rp "
            "  WHERE rp.role_id = r.id AND rp.permission_id = p.id"
            ")"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id = ("
            "  SELECT id FROM permissions WHERE code = 'dashboard:inventory'"
            ")"
        )
    )
    op.execute(
        sa.text("DELETE FROM permissions WHERE code = 'dashboard:inventory'")
    )
    op.drop_table("inventory_item_suppliers")
    op.drop_table("suppliers")
