"""add finance expense fk and clinical bcs constraint

Revision ID: b7c8d9e0f1a2
Revises: x9y8z7w6v5u4
Create Date: 2026-09-15 15:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "x9y8z7w6v5u4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add BCS check constraint on clinical_exams if not present
    constraint_check = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'ck_clinical_exams_bcs_1_9'"
        )
    ).scalar()
    if not constraint_check:
        op.create_check_constraint(
            "ck_clinical_exams_bcs_1_9",
            "clinical_exams",
            "body_condition_score >= 1 AND body_condition_score <= 9",
        )

    # 2. Add rescue_case_id and shelter_facility_id to finance_expenses if not present
    cols = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'finance_expenses'"
            )
        ).fetchall()
    }

    if "rescue_case_id" not in cols:
        op.add_column(
            "finance_expenses",
            sa.Column(
                "rescue_case_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("rescue_requests.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_finance_expenses_rescue_case_id",
            "finance_expenses",
            ["rescue_case_id"],
        )

    if "shelter_facility_id" not in cols:
        op.add_column(
            "finance_expenses",
            sa.Column(
                "shelter_facility_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("shelter_facilities.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_finance_expenses_shelter_facility_id",
            "finance_expenses",
            ["shelter_facility_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()

    cols = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'finance_expenses'"
            )
        ).fetchall()
    }

    if "shelter_facility_id" in cols:
        op.drop_index("ix_finance_expenses_shelter_facility_id", table_name="finance_expenses")
        op.drop_column("finance_expenses", "shelter_facility_id")

    if "rescue_case_id" in cols:
        op.drop_index("ix_finance_expenses_rescue_case_id", table_name="finance_expenses")
        op.drop_column("finance_expenses", "rescue_case_id")

    constraint_check = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'ck_clinical_exams_bcs_1_9'"
        )
    ).scalar()
    if constraint_check:
        op.drop_constraint("ck_clinical_exams_bcs_1_9", "clinical_exams", type_="check")
