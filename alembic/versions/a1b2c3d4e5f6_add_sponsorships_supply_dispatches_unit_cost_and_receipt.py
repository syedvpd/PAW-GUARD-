"""add sponsorships, supply dispatches, unit_cost, reference fields, receipt_key

- Creates dog_sponsorships table
- Adds sponsorship_id (FK) + receipt_file_key to donations
- Adds unit_cost to inventory_items
- Adds reference_type, reference_id to inventory_movements
- Creates foster_supply_dispatches table

Revision ID: a1b2c3d4e5f6
Revises: e8f9a0b1c2d3
Create Date: 2026-07-30 23:59:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # dog_sponsorships
    op.create_table(
        "dog_sponsorships",
        sa.Column("donor_id", sa.UUID(), nullable=False, index=True),
        sa.Column("dog_id", sa.UUID(), nullable=False),
        sa.Column("monthly_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("status", sa.String(length=32), nullable=False, index=True, server_default=sa.text("'active'")),
        sa.Column("next_charge_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["donor_id"], ["donor_profiles.id"], name=op.f("fk_dog_sponsorships_donor_id_donor_profiles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dog_id"], ["dog_profiles.id"], name=op.f("fk_dog_sponsorships_dog_id_dog_profiles"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dog_sponsorships")),
    )

    # donations: sponsorship_id FK
    op.add_column("donations", sa.Column("sponsorship_id", sa.UUID(), nullable=True, index=True))
    op.create_foreign_key(
        op.f("fk_donations_sponsorship_id_dog_sponsorships"),
        "donations", "dog_sponsorships",
        ["sponsorship_id"], ["id"],
        ondelete="SET NULL",
    )

    # donations: receipt_file_key
    op.add_column("donations", sa.Column("receipt_file_key", sa.String(length=512), nullable=True))

    # inventory_items: unit_cost
    op.add_column("inventory_items", sa.Column("unit_cost", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0.0")))

    # inventory_movements: reference_type, reference_id
    op.add_column("inventory_movements", sa.Column("reference_type", sa.String(length=64), nullable=True))
    op.add_column("inventory_movements", sa.Column("reference_id", sa.UUID(), nullable=True))

    # foster_supply_dispatches
    op.create_table(
        "foster_supply_dispatches",
        sa.Column("placement_id", sa.UUID(), nullable=False, index=True),
        sa.Column("dispatched_by_id", sa.UUID(), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["placement_id"], ["foster_placements.id"], name=op.f("fk_foster_supply_dispatches_placement_id_foster_placements"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dispatched_by_id"], ["users.id"], name=op.f("fk_foster_supply_dispatches_dispatched_by_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_foster_supply_dispatches")),
    )


def downgrade() -> None:
    op.drop_table("foster_supply_dispatches")
    op.drop_column("inventory_movements", "reference_id")
    op.drop_column("inventory_movements", "reference_type")
    op.drop_column("inventory_items", "unit_cost")
    op.drop_column("donations", "receipt_file_key")
    op.drop_constraint(op.f("fk_donations_sponsorship_id_dog_sponsorships"), "donations", type_="foreignkey")
    op.drop_column("donations", "sponsorship_id")
    op.drop_table("dog_sponsorships")
