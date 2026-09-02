"""create_report_media_table

Revision ID: 77d202d452ad
Revises: i5j6k7l8m9n0
Create Date: 2026-08-27 12:38:16.536830

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "77d202d452ad"
down_revision: str | None = "q3r4s5t6u7v8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "report_media" not in tables:
        # Create report_media table
        op.create_table(
            "report_media",
            sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("rescue_request_id", sa.UUID(), nullable=True),
            sa.Column("lost_report_id", sa.UUID(), nullable=True),
            sa.Column("found_report_id", sa.UUID(), nullable=True),
            sa.Column("media_type", sa.String(length=16), nullable=False),
            sa.Column("object_key", sa.String(length=512), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.UUID(), nullable=True),
            sa.Column("updated_by", sa.UUID(), nullable=True),
            sa.ForeignKeyConstraint(
                ["created_by"],
                ["users.id"],
                name=op.f("fk_report_media_created_by_users"),
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["found_report_id"],
                ["found_reports.id"],
                name=op.f("fk_report_media_found_report_id_found_reports"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["lost_report_id"],
                ["lost_reports.id"],
                name=op.f("fk_report_media_lost_report_id_lost_reports"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["rescue_request_id"],
                ["rescue_requests.id"],
                name=op.f("fk_report_media_rescue_request_id_rescue_requests"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["updated_by"],
                ["users.id"],
                name=op.f("fk_report_media_updated_by_users"),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_report_media")),
        )
        op.create_index(
            op.f("ix_report_media_created_at"), "report_media", ["created_at"], unique=False
        )
        op.create_index(
            op.f("ix_report_media_created_by"), "report_media", ["created_by"], unique=False
        )
        op.create_index(
            op.f("ix_report_media_deleted_at"), "report_media", ["deleted_at"], unique=False
        )
        op.create_index(
            op.f("ix_report_media_found_report_id"),
            "report_media",
            ["found_report_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_report_media_lost_report_id"), "report_media", ["lost_report_id"], unique=False
        )
        op.create_index(
            op.f("ix_report_media_rescue_request_id"),
            "report_media",
            ["rescue_request_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_report_media_updated_at"), "report_media", ["updated_at"], unique=False
        )
        op.create_index(
            op.f("ix_report_media_updated_by"), "report_media", ["updated_by"], unique=False
        )

        # Data Migration: Backfill existing lost_reports
        op.execute(
            """
            INSERT INTO report_media (id, lost_report_id, media_type, object_key, is_primary, display_order, created_at, updated_at)
            SELECT gen_random_uuid(), id, 'photo', photo_object_key, TRUE, 0, created_at, updated_at
            FROM lost_reports
            WHERE photo_object_key IS NOT NULL AND photo_object_key <> '';
            """
        )

        # Data Migration: Backfill existing found_reports
        op.execute(
            """
            INSERT INTO report_media (id, found_report_id, media_type, object_key, is_primary, display_order, created_at, updated_at)
            SELECT gen_random_uuid(), id, 'photo', photo_object_key, TRUE, 0, created_at, updated_at
            FROM found_reports
            WHERE photo_object_key IS NOT NULL AND photo_object_key <> '';
            """
        )

        # Data Migration: Backfill existing rescue_requests (media_evidence is a JSONB array of strings)
        op.execute(
            """
            INSERT INTO report_media (id, rescue_request_id, media_type, object_key, is_primary, display_order, created_at, updated_at)
            SELECT 
                gen_random_uuid(), 
                id, 
                CASE 
                    WHEN key_val LIKE '%.mp4' OR key_val LIKE '%.webm' OR key_val LIKE '%.mov' THEN 'video'
                    ELSE 'photo'
                END,
                key_val, 
                (idx = 0), 
                idx, 
                created_at, 
                updated_at
            FROM (
                SELECT id, created_at, updated_at, elem as key_val, ord - 1 as idx
                FROM rescue_requests,
                LATERAL jsonb_array_elements_text(media_evidence) WITH ORDINALITY AS arr(elem, ord)
                WHERE media_evidence IS NOT NULL AND jsonb_typeof(media_evidence) = 'array'
            ) sub;
            """
        )

        # Enable Row Level Security (RLS) on report_media for Supabase PostgREST lockdown
        op.execute("ALTER TABLE report_media ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "report_media" in tables:
        op.drop_index(op.f("ix_report_media_updated_by"), table_name="report_media")
        op.drop_index(op.f("ix_report_media_updated_at"), table_name="report_media")
        op.drop_index(op.f("ix_report_media_rescue_request_id"), table_name="report_media")
        op.drop_index(op.f("ix_report_media_lost_report_id"), table_name="report_media")
        op.drop_index(op.f("ix_report_media_found_report_id"), table_name="report_media")
        op.drop_index(op.f("ix_report_media_deleted_at"), table_name="report_media")
        op.drop_index(op.f("ix_report_media_created_by"), table_name="report_media")
        op.drop_index(op.f("ix_report_media_created_at"), table_name="report_media")
        op.drop_table("report_media")
