"""Seed script for default CMS pages shown on the public portal and managed via Admin CMS.

Populates the cms_pages, cms_sections, and cms_content_fields tables with
initial definitions for all standard public pages (home, about, adopt, etc.).
Re-running this script is idempotent: existing pages matched by slug are preserved.

Usage:
    python scripts/seed_cms_pages.py
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.portal.models import (
    CmsContentField,
    CmsPage,
    CmsSection,
    ContentStatus,
)
from pawguard.modules.portal.service import DEFAULT_CMS_PAGES_SEED


async def seed_cms_pages() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    now = datetime.now(UTC)
    created = 0
    existing_count = 0

    async with session_factory() as session:
        for seed in DEFAULT_CMS_PAGES_SEED:
            existing = (
                (
                    await session.execute(
                        select(CmsPage).where(CmsPage.slug == seed["slug"])
                    )
                )
                .scalars()
                .first()
            )
            if existing is not None:
                existing_count += 1
                continue

            page = CmsPage(
                id=uuid.uuid4(),
                slug=seed["slug"],
                name=seed["name"],
                description=seed.get("description"),
                seo_title=seed.get("seo_title"),
                seo_description=seed.get("seo_description"),
                seo_keywords=seed.get("seo_keywords"),
                status=ContentStatus.PUBLISHED,
                published_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(page)

            for s_data in seed.get("sections", []):
                sec = CmsSection(
                    id=uuid.uuid4(),
                    page_id=page.id,
                    section_key=s_data["key"],
                    section_name=s_data["name"],
                    display_order=s_data.get("display_order", 0),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                session.add(sec)

                for f_data in s_data.get("fields", []):
                    field = CmsContentField(
                        id=uuid.uuid4(),
                        section_id=sec.id,
                        field_key=f_data["key"],
                        field_type=f_data.get("type", "text"),
                        published_value=f_data.get("value"),
                        draft_value=f_data.get("value"),
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(field)

            created += 1

        await session.commit()
    await engine.dispose()
    print(f"Seed CMS pages completed ({created} new, {existing_count} existing).")


if __name__ == "__main__":
    asyncio.run(seed_cms_pages())
