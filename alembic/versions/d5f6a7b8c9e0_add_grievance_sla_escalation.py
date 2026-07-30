"""add_grievance_sla_escalation

Grievance tickets had no SLA deadline tracking, first-response timestamp, or
escalation path - PRR 3.14 requires "mandatory response SLAs, resolution
logging, and escalation paths"; only resolution logging existed.

Revision ID: d5f6a7b8c9e0
Revises: c4e5f6a7b8d9
Create Date: 2026-07-30 22:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5f6a7b8c9e0"
down_revision: Union[str, None] = "c4e5f6a7b8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "grievance_tickets",
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "grievance_tickets",
        sa.Column("first_responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "grievance_tickets",
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "grievance_tickets",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "grievance_tickets",
        sa.Column("escalated_to_admin_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_grievance_tickets_escalated_to_admin_id_users",
        "grievance_tickets", "users",
        ["escalated_to_admin_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_grievance_tickets_escalated_to_admin_id_users",
        "grievance_tickets", type_="foreignkey",
    )
    op.drop_column("grievance_tickets", "escalated_to_admin_id")
    op.drop_column("grievance_tickets", "escalated_at")
    op.drop_column("grievance_tickets", "escalation_level")
    op.drop_column("grievance_tickets", "first_responded_at")
    op.drop_column("grievance_tickets", "sla_due_at")
