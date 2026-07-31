"""Unit tests for PortalService with mocked repository and session."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.modules.portal.models import (
    BlogPost,
    ContactLocation,
    ContentStatus,
    FAQEntry,
    SuccessStory,
    VeterinaryPartner,
)
from pawguard.modules.portal.repository import PortalRepository
from pawguard.modules.portal.schemas import (
    BlogPostCreate,
    BlogPostUpdate,
    ContactLocationCreate,
    ContactLocationUpdate,
    FAQEntryCreate,
    FAQEntryUpdate,
    SuccessStoryCreate,
    SuccessStoryUpdate,
    VeterinaryPartnerCreate,
    VeterinaryPartnerUpdate,
)
from pawguard.modules.portal.service import PortalService
from pawguard.modules.settings.models import SystemSetting


class TestPortalService:
    @pytest.fixture
    def mock_repo(self):
        return AsyncMock(spec=PortalRepository)

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_repo, mock_session):
        return PortalService(mock_repo, mock_session)

    @pytest.mark.asyncio
    async def test_create_story(self, service, mock_repo):
        story_id = uuid.uuid4()
        mock_repo.create_story.return_value = SuccessStory(
            id=story_id, title="Happy Tail", summary="Summary", body="Body",
            status=ContentStatus.DRAFT,
        )
        payload = SuccessStoryCreate(title="Happy Tail", summary="Summary", body="Body")
        result = await service.create_story(payload)
        assert result.title == "Happy Tail"

    @pytest.mark.asyncio
    async def test_create_story_published(self, service, mock_repo):
        story_id = uuid.uuid4()
        mock_repo.create_story.return_value = SuccessStory(
            id=story_id, title="Story", summary="Sum", body="Body",
            status=ContentStatus.PUBLISHED, published_at=datetime.now(UTC),
        )
        payload = SuccessStoryCreate(title="Story", summary="Sum", body="Body", status=ContentStatus.PUBLISHED)
        result = await service.create_story(payload)
        assert result.status == ContentStatus.PUBLISHED

    @pytest.mark.asyncio
    async def test_update_story(self, service, mock_repo):
        story_id = uuid.uuid4()
        story = SuccessStory(
            id=story_id, title="Old", summary="Sum", body="Body",
            status=ContentStatus.DRAFT,
        )
        mock_repo.get_story.return_value = story
        payload = SuccessStoryUpdate(title="Updated")
        result = await service.update_story(story_id, payload)
        assert result.title == "Updated"

    @pytest.mark.asyncio
    async def test_update_story_not_found(self, service, mock_repo):
        mock_repo.get_story.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_story(uuid.uuid4(), SuccessStoryUpdate())

    @pytest.mark.asyncio
    async def test_get_story(self, service, mock_repo):
        story_id = uuid.uuid4()
        mock_repo.get_story.return_value = SuccessStory(
            id=story_id, title="T", summary="S", body="B",
            status=ContentStatus.PUBLISHED,
        )
        result = await service.get_story(story_id, published_only=True)
        assert result.id == story_id

    @pytest.mark.asyncio
    async def test_get_story_not_found_published_only(self, service, mock_repo):
        story = SuccessStory(
            id=uuid.uuid4(), title="T", summary="S", body="B",
            status=ContentStatus.DRAFT,
        )
        mock_repo.get_story.return_value = story
        with pytest.raises(NotFoundError):
            await service.get_story(uuid.uuid4(), published_only=True)

    @pytest.mark.asyncio
    async def test_list_stories(self, service, mock_repo):
        story = SuccessStory(id=uuid.uuid4(), title="T", summary="S", body="B", status=ContentStatus.PUBLISHED)
        mock_repo.list_stories.return_value = [story]
        results = await service.list_stories(published_only=True)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_stories_paginated(self, service, mock_repo):
        story = SuccessStory(id=uuid.uuid4(), title="T", summary="S", body="B", status=ContentStatus.DRAFT)
        mock_repo.count_stories.return_value = 1
        mock_repo.list_stories.return_value = [story]
        stories, meta = await service.list_stories_paginated()
        assert len(stories) == 1
        assert meta.total == 1

    @pytest.mark.asyncio
    async def test_create_blog(self, service, mock_repo):
        mock_repo.get_blog_by_slug.return_value = None
        blog_id = uuid.uuid4()
        mock_repo.create_blog.return_value = BlogPost(
            id=blog_id, title="Post", slug="my-post", excerpt="Exc",
            body="Body", category="awareness", status=ContentStatus.DRAFT,
        )
        payload = BlogPostCreate(title="Post", slug="my-post", excerpt="Exc", body="Body")
        result = await service.create_blog(payload)
        assert result.title == "Post"

    @pytest.mark.asyncio
    async def test_create_blog_duplicate_slug(self, service, mock_repo):
        mock_repo.get_blog_by_slug.return_value = BlogPost(
            id=uuid.uuid4(), title="Existing", slug="my-post", excerpt="E",
            body="B", category="a", status=ContentStatus.DRAFT,
        )
        payload = BlogPostCreate(title="Post", slug="my-post", excerpt="Exc", body="Body")
        with pytest.raises(ConflictError, match="slug.*already exists"):
            await service.create_blog(payload)

    @pytest.mark.asyncio
    async def test_update_blog(self, service, mock_repo):
        post_id = uuid.uuid4()
        post = BlogPost(
            id=post_id, title="Old", slug="old-post", excerpt="E",
            body="B", category="a", status=ContentStatus.DRAFT,
        )
        mock_repo.get_blog_by_id.return_value = post
        payload = BlogPostUpdate(title="Updated")
        result = await service.update_blog(post_id, payload)
        assert result.title == "Updated"

    @pytest.mark.asyncio
    async def test_update_blog_slug_conflict(self, service, mock_repo):
        post_id = uuid.uuid4()
        post = BlogPost(
            id=post_id, title="Old", slug="old-slug", excerpt="E",
            body="B", category="a", status=ContentStatus.DRAFT,
        )
        mock_repo.get_blog_by_id.return_value = post
        mock_repo.get_blog_by_slug.return_value = BlogPost(
            id=uuid.uuid4(), title="Other", slug="new-slug", excerpt="E",
            body="B", category="a", status=ContentStatus.DRAFT,
        )
        payload = BlogPostUpdate(slug="new-slug")
        with pytest.raises(ConflictError, match="slug.*already exists"):
            await service.update_blog(post_id, payload)

    @pytest.mark.asyncio
    async def test_get_blog(self, service, mock_repo):
        post_id = uuid.uuid4()
        mock_repo.get_blog_by_id.return_value = BlogPost(
            id=post_id, title="P", slug="p", excerpt="E", body="B",
            category="a", status=ContentStatus.PUBLISHED,
        )
        result = await service.get_blog(post_id, published_only=True)
        assert result.id == post_id

    @pytest.mark.asyncio
    async def test_get_blog_by_slug(self, service, mock_repo):
        mock_repo.get_blog_by_slug.return_value = BlogPost(
            id=uuid.uuid4(), title="P", slug="my-slug", excerpt="E", body="B",
            category="a", status=ContentStatus.PUBLISHED,
        )
        result = await service.get_blog_by_slug("my-slug", published_only=True)
        assert result.title == "P"

    @pytest.mark.asyncio
    async def test_create_vet(self, service, mock_repo):
        vet_id = uuid.uuid4()
        mock_repo.create_vet.return_value = VeterinaryPartner(
            id=vet_id, name="Vet Clinic", address="Addr", phone="+12345",
            is_emergency=False, is_active=True,
        )
        payload = VeterinaryPartnerCreate(name="Vet Clinic", address="Addr", phone="+12345")
        result = await service.create_vet(payload)
        assert result.name == "Vet Clinic"

    @pytest.mark.asyncio
    async def test_update_vet(self, service, mock_repo):
        vet_id = uuid.uuid4()
        vet = VeterinaryPartner(
            id=vet_id, name="Old", address="A", phone="+12345",
            is_emergency=False, is_active=True,
        )
        mock_repo.get_vet.return_value = vet
        payload = VeterinaryPartnerUpdate(name="Updated")
        result = await service.update_vet(vet_id, payload)
        assert result.name == "Updated"

    @pytest.mark.asyncio
    async def test_update_vet_not_found(self, service, mock_repo):
        mock_repo.get_vet.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_vet(uuid.uuid4(), VeterinaryPartnerUpdate())

    @pytest.mark.asyncio
    async def test_create_contact(self, service, mock_repo):
        loc_id = uuid.uuid4()
        mock_repo.create_contact.return_value = ContactLocation(
            id=loc_id, name="Office", address="Addr", phone="+12345",
        )
        payload = ContactLocationCreate(name="Office", address="Addr", phone="+12345")
        result = await service.create_contact(payload)
        assert result.name == "Office"

    @pytest.mark.asyncio
    async def test_update_contact(self, service, mock_repo):
        loc_id = uuid.uuid4()
        loc = ContactLocation(id=loc_id, name="Old", address="A", phone="+12345")
        mock_repo.get_contact.return_value = loc
        payload = ContactLocationUpdate(name="Updated")
        result = await service.update_contact(loc_id, payload)
        assert result.name == "Updated"

    @pytest.mark.asyncio
    async def test_create_faq(self, service, mock_repo):
        faq_id = uuid.uuid4()
        mock_repo.create_faq.return_value = FAQEntry(
            id=faq_id, question="Q?", answer="A!", category="general",
            is_published=True,
        )
        payload = FAQEntryCreate(question="Q?", answer="A!")
        result = await service.create_faq(payload)
        assert result.question == "Q?"

    @pytest.mark.asyncio
    async def test_update_faq(self, service, mock_repo):
        faq_id = uuid.uuid4()
        faq = FAQEntry(id=faq_id, question="Q?", answer="A!", category="general", is_published=True)
        mock_repo.get_faq.return_value = faq
        payload = FAQEntryUpdate(answer="Updated!")
        result = await service.update_faq(faq_id, payload)
        assert result.answer == "Updated!"

    @pytest.mark.asyncio
    async def test_upsert_setting_new(self, service, mock_repo):
        mock_repo.get_setting.return_value = None
        setting = SystemSetting(key="app.name", value="PawGuard", description="App name")
        mock_repo.upsert_setting.return_value = setting
        result = await service.upsert_setting("app.name", "PawGuard", "App name")
        assert result.value == "PawGuard"

    @pytest.mark.asyncio
    async def test_upsert_setting_existing(self, service, mock_repo):
        setting = SystemSetting(key="app.name", value="Old", description="Desc")
        mock_repo.get_setting.return_value = setting
        result = await service.upsert_setting("app.name", "New", None)
        assert result.value == "New"

    @pytest.mark.asyncio
    async def test_get_setting(self, service, mock_repo):
        mock_repo.get_setting.return_value = SystemSetting(key="app.name", value="PawGuard", description="App")
        result = await service.get_setting("app.name")
        assert result.value == "PawGuard"

    @pytest.mark.asyncio
    async def test_get_setting_not_found(self, service, mock_repo):
        mock_repo.get_setting.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_setting("nonexistent")

    @pytest.mark.asyncio
    async def test_soft_delete_story(self, service, mock_repo):
        story_id = uuid.uuid4()
        mock_repo.get_story.return_value = SuccessStory(
            id=story_id, title="T", summary="S", body="B", status=ContentStatus.DRAFT,
        )
        mock_repo.soft_delete_story.return_value = None
        await service.soft_delete_story(story_id)
        mock_repo.soft_delete_story.assert_called_once_with(story_id)

    @pytest.mark.asyncio
    async def test_soft_delete_blog(self, service, mock_repo):
        post_id = uuid.uuid4()
        mock_repo.get_blog_by_id.return_value = BlogPost(
            id=post_id, title="P", slug="p", excerpt="E", body="B",
            category="a", status=ContentStatus.DRAFT,
        )
        mock_repo.soft_delete_blog.return_value = None
        await service.soft_delete_blog(post_id)
        mock_repo.soft_delete_blog.assert_called_once_with(post_id)

    @pytest.mark.asyncio
    async def test_soft_delete_faq(self, service, mock_repo):
        faq_id = uuid.uuid4()
        mock_repo.get_faq.return_value = FAQEntry(
            id=faq_id, question="Q?", answer="A!", category="general", is_published=True,
        )
        mock_repo.soft_delete_faq.return_value = None
        await service.soft_delete_faq(faq_id)
        mock_repo.soft_delete_faq.assert_called_once_with(faq_id)

    @pytest.mark.asyncio
    async def test_get_hero_stats(self, service, mock_session):
        def scalar_one():
            return 10
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        mock_session.execute.return_value = mock_result
        stats = await service.get_hero_stats()
        assert stats.total_rescued == 10
        assert stats.active_care_count == 10
        assert stats.successful_adoptions == 10
        assert stats.urgent_rescue_count == 10
