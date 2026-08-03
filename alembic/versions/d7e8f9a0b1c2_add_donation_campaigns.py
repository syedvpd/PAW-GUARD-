"""add_donation_campaigns

PRR 3.1.7 / 3.11: goal-oriented fundraising campaigns.

- Creates the `donation_campaigns` table (name, target, status, window,
  type) so the public site and admin portal can run goal-driven drives.
- Adds `campaign_id` to `donations` so contributions can be attributed to
  a campaign; campaign progress (raised amount / donor count) is derived
  from successful donations at read time.

Revision ID: d7e8f9a0b1c2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-03 08:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "donation_campaigns",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("campaign_type", sa.String(length=32), server_default="general", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("goal_reached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name=op.f("fk_donation_campaigns_created_by_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_donation_campaigns")),
    )
    op.create_index(
        op.f("ix_donation_campaigns_status"), "donation_campaigns", ["status"], unique=False
    )

    op.add_column(
        "donations",
        sa.Column("campaign_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_donations_campaign_id"), "donations", ["campaign_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_donations_campaign_id_donation_campaigns"),
        "donations", "donation_campaigns", ["campaign_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_donations_campaign_id_donation_campaigns"),
        "donations", type_="foreignkey",
    )
    op.drop_index(op.f("ix_donations_campaign_id"), table_name="donations")
    op.drop_column("donations", "campaign_id")
    op.drop_index(op.f("ix_donation_campaigns_status"), table_name="donation_campaigns")
    op.drop_table("donation_campaigns")
