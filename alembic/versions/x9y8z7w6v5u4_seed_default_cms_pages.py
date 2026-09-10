"""seed_default_cms_pages

Revision ID: x9y8z7w6v5u4
Revises: w2b3c4d5e6f7
Create Date: 2026-09-09 10:30:00.000000

"""

import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from pawguard.modules.portal.service import DEFAULT_CMS_PAGES_SEED

# revision identifiers, used by Alembic.
revision: str = "x9y8z7w6v5u4"
down_revision: Union[str, None] = "c5d6e7f8a9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)

    # Check which slugs exist
    existing_result = conn.execute(sa.text("SELECT slug FROM cms_pages WHERE deleted_at IS NULL"))
    existing_slugs = {row[0] for row in existing_result.fetchall()}

    for seed in DEFAULT_CMS_PAGES_SEED:
        slug = seed["slug"]
        if slug in existing_slugs:
            continue

        page_id = uuid.uuid4()
        conn.execute(
            sa.text(
                """
                INSERT INTO cms_pages (
                    id, slug, name, description, seo_title, seo_description, seo_keywords,
                    status, published_at, created_at, updated_at
                ) VALUES (
                    :id, :slug, :name, :description, :seo_title, :seo_description, :seo_keywords,
                    'published', :now, :now, :now
                )
                """
            ),
            {
                "id": page_id,
                "slug": slug,
                "name": seed["name"],
                "description": seed.get("description"),
                "seo_title": seed.get("seo_title"),
                "seo_description": seed.get("seo_description"),
                "seo_keywords": seed.get("seo_keywords"),
                "now": now,
            },
        )

        for s_data in seed.get("sections", []):
            section_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    """
                    INSERT INTO cms_sections (
                        id, page_id, section_key, section_name, display_order, is_active,
                        created_at, updated_at
                    ) VALUES (
                        :id, :page_id, :section_key, :section_name, :display_order, true,
                        :now, :now
                    )
                    """
                ),
                {
                    "id": section_id,
                    "page_id": page_id,
                    "section_key": s_data["key"],
                    "section_name": s_data["name"],
                    "display_order": s_data.get("display_order", 0),
                    "now": now,
                },
            )

            for f_data in s_data.get("fields", []):
                field_id = uuid.uuid4()
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO cms_content_fields (
                            id, section_id, field_key, field_type, published_value, draft_value,
                            created_at, updated_at
                        ) VALUES (
                            :id, :section_id, :field_key, :field_type, :val, :val,
                            :now, :now
                        )
                        """
                    ),
                    {
                        "id": field_id,
                        "section_id": section_id,
                        "field_key": f_data["key"],
                        "field_type": f_data.get("type", "text"),
                        "val": f_data.get("value"),
                        "now": now,
                    },
                )


def downgrade() -> None:
    # No-op downgrade so user-edited content isn't accidentally deleted
    pass
