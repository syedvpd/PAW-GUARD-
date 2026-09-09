"""Unit & Integration tests for PawGuard Dynamic CMS Module & Public/Admin Sync."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.modules.auth.service import RequestContext
from pawguard.modules.portal.models import CmsPage, ContentStatus, SuccessStory
from pawguard.modules.portal.repository import PortalRepository
from pawguard.modules.portal.schemas import (
    CmsFieldUpdate,
    CmsPageUpdate,
    CmsSectionUpdate,
    ContactMessageCreate,
    NewsletterSubscribeRequest,
    SuccessStoryUpdate,
)
from pawguard.modules.portal.service import PortalService


class TestCmsModule:
    @pytest.fixture
    def setup_service(self):
        session = AsyncMock()
        repo = MagicMock(spec=PortalRepository)
        db_pages: list[CmsPage] = []
        db_stories: list[SuccessStory] = []

        async def mock_list():
            return list(db_pages)

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

        async def mock_count_stories(status=None, search=None, is_featured=None):
            count = 0
            for s in db_stories:
                if status and s.status != status:
                    continue
                if is_featured is not None and s.is_featured != is_featured:
                    continue
                if (
                    search
                    and search.lower() not in s.title.lower()
                    and search.lower() not in s.body.lower()
                ):
                    continue
                count += 1
            return count

        async def mock_list_stories(
            published_only=False,
            page_params=None,
            status=None,
            search=None,
            sort=None,
            is_featured=None,
        ):
            results = []
            for s in db_stories:
                if published_only and s.status != ContentStatus.PUBLISHED:
                    continue
                if status and s.status != status:
                    continue
                if is_featured is not None and s.is_featured != is_featured:
                    continue
                if (
                    search
                    and search.lower() not in s.title.lower()
                    and search.lower() not in s.body.lower()
                ):
                    continue
                results.append(s)
            return results

        async def mock_get_story(story_id):
            for s in db_stories:
                if s.id == story_id:
                    return s
            return None

        async def mock_create_story(story):
            db_stories.append(story)
            return story

        async def mock_save_story():
            pass

        repo.list_cms_pages = AsyncMock(side_effect=mock_list)
        repo.create_cms_page = AsyncMock(side_effect=mock_create)
        repo.get_cms_page_by_slug = AsyncMock(side_effect=mock_get)
        repo.save_cms_page = AsyncMock(side_effect=mock_save)
        repo.create_cms_page_version = AsyncMock(side_effect=mock_create_version)

        repo.count_stories = AsyncMock(side_effect=mock_count_stories)
        repo.list_stories = AsyncMock(side_effect=mock_list_stories)
        repo.get_story = AsyncMock(side_effect=mock_get_story)
        repo.create_story = AsyncMock(side_effect=mock_create_story)
        repo.save_story = AsyncMock(side_effect=mock_save_story)

        service = PortalService(repository=repo, session=session)
        return service, db_pages, db_stories

    @pytest.mark.asyncio
    async def test_cms_service_seed_and_get_public_page(self, setup_service):
        service, db_pages, _ = setup_service

        public_home = await service.get_public_cms_page("home")
        assert public_home.slug == "home"
        assert public_home.name == "Home Page"
        assert "hero" in public_home.sections
        assert public_home.sections["hero"]["title"] == "Find Your New Best Friend..."
        assert public_home.sections["hero"]["primary_cta_text"] == "Adopt a Pet"

    @pytest.mark.asyncio
    async def test_home_page_lazy_creation_and_per_slug_seeding(self, setup_service):
        service, db_pages, _ = setup_service

        # Simulate database having only "about" page initially
        now = datetime.now(UTC)
        about_page = CmsPage(
            id=uuid.uuid4(),
            slug="about",
            name="About & Mission",
            status=ContentStatus.PUBLISHED,
            published_at=now,
            created_at=now,
            updated_at=now,
        )
        about_page.sections = []
        about_page.versions = []
        db_pages.append(about_page)

        # Calling get_admin_cms_page("home") must NOT return 404, but rather seed "home"
        home_page = await service.get_admin_cms_page("home")
        assert home_page.slug == "home"
        assert home_page.name == "Home Page"
        assert len(home_page.sections) >= 3

    @pytest.mark.asyncio
    async def test_contact_and_newsletter_only_accept_registered_users(self):
        session = AsyncMock()
        repo = MagicMock(spec=PortalRepository)
        arq = AsyncMock()
        service = PortalService(repository=repo, session=session, arq_pool=arq)
        user = MagicMock(id=uuid.uuid4(), email="member@example.com")
        repo.get_active_user_by_email = AsyncMock(return_value=user)
        repo.create_contact_message = AsyncMock()
        repo.get_newsletter_subscription = AsyncMock(return_value=None)
        repo.create_newsletter_subscription = AsyncMock()

        assert (
            await service.submit_contact_message(
                ContactMessageCreate(
                    email=user.email, subject="Help", message="I need adoption support."
                )
            )
            is True
        )
        assert (
            await service.subscribe_newsletter(NewsletterSubscribeRequest(email=user.email)) is True
        )
        assert arq.enqueue_job.await_count == 2

        repo.get_active_user_by_email.return_value = None
        assert (
            await service.submit_contact_message(
                ContactMessageCreate(email="unknown@example.com", subject="Spam", message="No")
            )
            is False
        )
        assert (
            await service.subscribe_newsletter(
                NewsletterSubscribeRequest(email="unknown@example.com")
            )
            is False
        )
        assert arq.enqueue_job.await_count == 2

    @pytest.mark.asyncio
    async def test_cms_draft_edit_discard_and_publish_flow(self, setup_service):
        service, db_pages, _ = setup_service

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
            "home",
            update_payload,
            user_id=uuid.uuid4(),
            ctx=RequestContext(ip_address="127.0.0.1", user_agent="pytest"),
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

    @pytest.mark.asyncio
    async def test_success_stories_admin_and_public_sync_and_filtering(self, setup_service):
        service, _, db_stories = setup_service

        now = datetime.now(UTC)
        story1 = SuccessStory(
            id=uuid.uuid4(),
            title="Bruno's Long Journey",
            summary="From streets to sofa",
            body="Bruno was found injured and now lives happily.",
            status=ContentStatus.PUBLISHED,
            is_featured=True,
            sort_order=1,
            published_at=now,
            created_at=now,
            updated_at=now,
        )
        story2 = SuccessStory(
            id=uuid.uuid4(),
            title="Bella's New Family",
            summary="Found a forever home",
            body="Bella found her loving humans.",
            status=ContentStatus.DRAFT,
            is_featured=False,
            sort_order=2,
            published_at=None,
            created_at=now,
            updated_at=now,
        )
        db_stories.extend([story1, story2])

        # 1. Public listing only returns published stories
        pub_stories = await service.list_stories(published_only=True)
        assert len(pub_stories) == 1
        assert pub_stories[0].id == story1.id

        # 2. Admin listing returns ALL stories by default (published + draft)
        admin_all, meta = await service.list_stories_paginated()
        assert meta.total == 2
        assert len(admin_all) == 2
        # Verify the same underlying object is returned
        assert admin_all[0].id == story1.id
        assert admin_all[1].id == story2.id

        # 3. Admin filter by status=published
        admin_pub, pub_meta = await service.list_stories_paginated(status=ContentStatus.PUBLISHED)
        assert pub_meta.total == 1
        assert admin_pub[0].id == story1.id

        # 4. Admin filter by is_featured=True
        featured_stories, feat_meta = await service.list_stories_paginated(is_featured=True)
        assert feat_meta.total == 1
        assert featured_stories[0].id == story1.id

        # 5. Admin filter by is_featured=False
        non_feat, non_meta = await service.list_stories_paginated(is_featured=False)
        assert non_meta.total == 1
        assert non_feat[0].id == story2.id

        # 6. Admin search
        searched, s_meta = await service.list_stories_paginated(search="Bruno")
        assert s_meta.total == 1
        assert searched[0].title == "Bruno's Long Journey"

        # 7. Edit existing story does NOT create a duplicate
        update_payload = SuccessStoryUpdate(summary="Updated Bruno summary")
        updated_story = await service.update_story(story1.id, update_payload)
        assert updated_story.id == story1.id
        assert updated_story.summary == "Updated Bruno summary"
        assert len(db_stories) == 2  # No duplicate record created!
