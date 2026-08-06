"""Unit & Integration tests for PawGuard Dynamic CMS Module."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.modules.auth.service import RequestContext
from pawguard.modules.portal.models import CmsPage, ContentStatus
from pawguard.modules.portal.repository import PortalRepository
from pawguard.modules.portal.schemas import CmsFieldUpdate, CmsPageUpdate, CmsSectionUpdate
from pawguard.modules.portal.service import PortalService


class TestCmsModule:
    @pytest.fixture
    def setup_service(self):
        session = AsyncMock()
        repo = MagicMock(spec=PortalRepository)
        db_pages: list[CmsPage] = []

        async def mock_list():
            return db_pages

        async def mock_create(page: CmsPage):
            db_pages.append(page)
            return page

        async def mock_get(slug: str):
            for p in db_pages:
                if p.slug == slug:
                    return p
            return None

        async def mock_save():
            pass

        async def mock_create_version(v):
            return v

        repo.list_cms_pages = AsyncMock(side_effect=mock_list)
        repo.create_cms_page = AsyncMock(side_effect=mock_create)
        repo.get_cms_page_by_slug = AsyncMock(side_effect=mock_get)
        repo.save_cms_page = AsyncMock(side_effect=mock_save)
        repo.create_cms_page_version = AsyncMock(side_effect=mock_create_version)

        service = PortalService(repository=repo, session=session)
        return service, db_pages

    @pytest.mark.asyncio
    async def test_cms_service_seed_and_get_public_page(self, setup_service):
        service, db_pages = setup_service

        public_home = await service.get_public_cms_page("home")
        assert public_home.slug == "home"
        assert public_home.name == "Home Page"
        assert "hero" in public_home.sections
        assert public_home.sections["hero"]["title"] == "Find Your New Best Friend..."
        assert public_home.sections["hero"]["primary_cta_text"] == "Adopt a Pet"

    @pytest.mark.asyncio
    async def test_cms_draft_edit_discard_and_publish_flow(self, setup_service):
        service, db_pages = setup_service

        # 1. Seed Home page
        page_resp = await service.get_admin_cms_page("home")
        assert page_resp.status == ContentStatus.PUBLISHED

        # 2. Edit draft title to "Find Your New Lucky Dog..."
        update_payload = CmsPageUpdate(
            sections=[
                CmsSectionUpdate(
                    section_key="hero",
                    fields=[
                        CmsFieldUpdate(field_key="title", value="Find Your New Lucky Dog..."),
                    ],
                )
            ]
        )
        updated = await service.update_admin_cms_page(
            "home", update_payload, user_id=uuid.uuid4(), ctx=RequestContext(ip_address="127.0.0.1", user_agent="pytest")
        )
        assert updated.status == ContentStatus.DRAFT

        # 3. Verify public API still returns published title "Find Your New Best Friend..."
        public_before_publish = await service.get_public_cms_page("home")
        assert public_before_publish.sections["hero"]["title"] == "Find Your New Best Friend..."

        # 4. Discard draft changes
        discarded = await service.discard_admin_cms_page("home")
        assert discarded.status == ContentStatus.PUBLISHED

        # 5. Re-edit draft title and Publish
        await service.update_admin_cms_page("home", update_payload)
        published = await service.publish_admin_cms_page("home", user_id=uuid.uuid4())
        assert published.status == ContentStatus.PUBLISHED

        # 6. Verify public API now returns updated published title "Find Your New Lucky Dog..."
        public_after_publish = await service.get_public_cms_page("home")
        assert public_after_publish.sections["hero"]["title"] == "Find Your New Lucky Dog..."
