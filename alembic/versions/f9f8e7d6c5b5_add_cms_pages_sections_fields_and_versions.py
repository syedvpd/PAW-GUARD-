"""add_cms_pages_sections_fields_and_versions

Create cms_pages, cms_sections, cms_content_fields, and cms_page_versions tables.

Revision ID: f9f8e7d6c5b5
Revises: f9f8e7d6c5b4
Create Date: 2026-08-06 11:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f9f8e7d6c5b5"
down_revision: Union[str, None] = "f9f8e7d6c5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cms_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("seo_title", sa.String(length=255), nullable=True),
        sa.Column("seo_description", sa.Text(), nullable=True),
        sa.Column("seo_keywords", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cms_pages_slug", "cms_pages", ["slug"], unique=True)
    op.create_index("ix_cms_pages_status", "cms_pages", ["status"])

    op.create_table(
        "cms_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cms_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_key", sa.String(length=64), nullable=False),
        sa.Column("section_name", sa.String(length=128), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cms_sections_page_id", "cms_sections", ["page_id"])
    op.create_index("ix_cms_sections_section_key", "cms_sections", ["section_key"])

    op.create_table(
        "cms_content_fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cms_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_key", sa.String(length=64), nullable=False),
        sa.Column("field_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("published_value", sa.Text(), nullable=True),
        sa.Column("draft_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cms_content_fields_section_id", "cms_content_fields", ["section_id"])
    op.create_index("ix_cms_content_fields_field_key", "cms_content_fields", ["field_key"])

    op.create_table(
        "cms_page_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cms_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cms_page_versions_page_id", "cms_page_versions", ["page_id"])


def downgrade() -> None:
    op.drop_table("cms_page_versions")
    op.drop_table("cms_content_fields")
    op.drop_table("cms_sections")
    op.drop_table("cms_pages")
