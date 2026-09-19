"""add adoption applicant documents, document verification and score type

Revision ID: g5b6c7d8e9f0
Revises: f4a1b2c3d4e5
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "g5b6c7d8e9f0"
down_revision: Union[str, None] = "f4a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "adoption_applications",
        sa.Column("applicant_documents", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "adoption_applications",
        sa.Column("documents_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "adoption_applications",
        sa.Column("documents_verified_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_adoption_applications_documents_verified_by_id_users",
        "adoption_applications",
        "users",
        ["documents_verified_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "adoption_scores",
        sa.Column("score_type", sa.String(length=16), server_default="interview", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("adoption_scores", "score_type")
    op.drop_constraint(
        "fk_adoption_applications_documents_verified_by_id_users",
        "adoption_applications",
        type_="foreignkey",
    )
    op.drop_column("adoption_applications", "documents_verified_by_id")
    op.drop_column("adoption_applications", "documents_verified_at")
    op.drop_column("adoption_applications", "applicant_documents")
