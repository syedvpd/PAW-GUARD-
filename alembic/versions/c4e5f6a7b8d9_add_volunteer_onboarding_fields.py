"""add_volunteer_onboarding_fields

VolunteerProfile was missing background-check, medical-conditions, and
animal-handling-experience fields required by PRR 3.9's onboarding/skills
matrix - they existed nowhere in the model, only a free-text `skills` field.

Revision ID: c4e5f6a7b8d9
Revises: b3d4e5f6a7c8
Create Date: 2026-07-30 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4e5f6a7b8d9"
down_revision: Union[str, None] = "b3d4e5f6a7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "volunteer_profiles",
        sa.Column(
            "background_check_completed", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "volunteer_profiles",
        sa.Column("background_check_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "volunteer_profiles",
        sa.Column("medical_conditions", sa.Text(), nullable=True),
    )
    op.add_column(
        "volunteer_profiles",
        sa.Column("animal_handling_experience", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("volunteer_profiles", "animal_handling_experience")
    op.drop_column("volunteer_profiles", "medical_conditions")
    op.drop_column("volunteer_profiles", "background_check_notes")
    op.drop_column("volunteer_profiles", "background_check_completed")
