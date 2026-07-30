"""add adoption scoring, foster progress logs, and fleet fuel/insurance

- Creates adoption_scores table (interview/inspection scoring for adoptions)
- Creates foster_progress_logs table (daily weight/behavior/medication logs)
- Adds insurance columns to vehicles table
- Creates fuel_logs table (fuel tracking with mileage)

Revision ID: e8f9a0b1c2d3
Revises: 783f541d2d75
Create Date: 2026-07-30 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "783f541d2d75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # adoption_scores
    op.create_table(
        "adoption_scores",
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("scored_by_id", sa.UUID(), nullable=False),
        sa.Column("home_environment_score", sa.Integer(), nullable=False),
        sa.Column("pet_care_knowledge_score", sa.Integer(), nullable=False),
        sa.Column("financial_readiness_score", sa.Integer(), nullable=False),
        sa.Column("lifestyle_compatibility_score", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("recommendation", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["adoption_applications.id"], name=op.f("fk_adoption_scores_application_id_adoption_applications"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scored_by_id"], ["users.id"], name=op.f("fk_adoption_scores_scored_by_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_adoption_scores")),
    )
    op.create_index(op.f("ix_adoption_scores_application_id"), "adoption_scores", ["application_id"], unique=False)

    # foster_progress_logs
    op.create_table(
        "foster_progress_logs",
        sa.Column("placement_id", sa.UUID(), nullable=False),
        sa.Column("tracked_by_id", sa.UUID(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=True),
        sa.Column("behavior_notes", sa.Text(), nullable=True),
        sa.Column("feeding_notes", sa.Text(), nullable=True),
        sa.Column("medication_notes", sa.Text(), nullable=True),
        sa.Column("exercise_minutes", sa.Integer(), nullable=True),
        sa.Column("photo_urls", sa.JSON(), nullable=True),
        sa.Column("mood_rating", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["placement_id"], ["foster_placements.id"], name=op.f("fk_foster_progress_logs_placement_id_foster_placements"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tracked_by_id"], ["users.id"], name=op.f("fk_foster_progress_logs_tracked_by_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_foster_progress_logs")),
    )
    op.create_index(op.f("ix_foster_progress_logs_placement_id"), "foster_progress_logs", ["placement_id"], unique=False)

    # fleet insurance columns
    op.add_column("vehicles", sa.Column("insurance_provider", sa.String(length=255), nullable=True))
    op.add_column("vehicles", sa.Column("insurance_policy_number", sa.String(length=128), nullable=True))
    op.add_column("vehicles", sa.Column("insurance_expiry_date", sa.Date(), nullable=True))
    op.add_column("vehicles", sa.Column("insurance_contact_phone", sa.String(length=32), nullable=True))

    # fuel_logs
    op.create_table(
        "fuel_logs",
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("filled_by_id", sa.UUID(), nullable=True),
        sa.Column("fuel_type", sa.String(length=32), nullable=False),
        sa.Column("volume_litres", sa.Numeric(8, 2), nullable=False),
        sa.Column("cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("mileage_at_fill", sa.Integer(), nullable=False),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column("receipt_url", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], name=op.f("fk_fuel_logs_vehicle_id_vehicles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["filled_by_id"], ["users.id"], name=op.f("fk_fuel_logs_filled_by_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fuel_logs")),
    )


def downgrade() -> None:
    op.drop_table("fuel_logs")
    op.drop_column("vehicles", "insurance_contact_phone")
    op.drop_column("vehicles", "insurance_expiry_date")
    op.drop_column("vehicles", "insurance_policy_number")
    op.drop_column("vehicles", "insurance_provider")
    op.drop_index(op.f("ix_foster_progress_logs_placement_id"), table_name="foster_progress_logs")
    op.drop_table("foster_progress_logs")
    op.drop_index(op.f("ix_adoption_scores_application_id"), table_name="adoption_scores")
    op.drop_table("adoption_scores")
