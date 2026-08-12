"""add_high_scale_performance_indexes

Revision ID: a2b3c4d5e6f7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-12 10:30:00.000000

"""
from collections.abc import Sequence
from alembic import op

revision: str = 'a2b3c4d5e6f7'
down_revision: str | None = 'e1f2a3b4c5d6'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Notifications user unread stream index (user_id, is_read, created_at DESC)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_user_unread "
        "ON notifications (user_id, is_read, created_at DESC);"
    )

    # 2. Medical records dog timeline index (dog_id, examination_date DESC)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_medical_records_dog_exam_date "
        "ON medical_records (dog_id, examination_date DESC);"
    )

    # 3. Donations donor history and gateway order lookup indexes
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_donations_donor_created "
        "ON donations (donor_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_donations_gateway_order "
        "ON donations (gateway_order_id) WHERE gateway_order_id IS NOT NULL;"
    )

    # 4. Grievance tickets status and SLA escalation index
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_grievance_tickets_status_sla "
        "ON grievance_tickets (status, created_at DESC) WHERE deleted_at IS NULL;"
    )

    # 5. Sponsorships due charges partial index (status, next_charge_date)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dog_sponsorships_due_charge "
        "ON dog_sponsorships (status, next_charge_date) WHERE status = 'ACTIVE';"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notifications_user_unread;")
    op.execute("DROP INDEX IF EXISTS ix_medical_records_dog_exam_date;")
    op.execute("DROP INDEX IF EXISTS ix_donations_donor_created;")
    op.execute("DROP INDEX IF EXISTS ix_donations_gateway_order;")
    op.execute("DROP INDEX IF EXISTS ix_grievance_tickets_status_sla;")
    op.execute("DROP INDEX IF EXISTS ix_dog_sponsorships_due_charge;")
