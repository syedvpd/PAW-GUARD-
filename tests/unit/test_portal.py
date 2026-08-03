"""Unit tests for PortalService with mocked repository and session."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.modules.portal.models import (
    AlertSeverity,
    BlogPost,
    ContactLocation,
    ContentStatus,
    FAQEntry,
    LegalDocument,
    LegalDocumentType,
    SuccessStory,
    UrgentAlert,
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
    LegalDocumentCreate,
    LegalDocumentUpdate,
    SuccessStoryCreate,
    SuccessStoryUpdate,
    UrgentAlertCreate,
    UrgentAlertUpdate,
    VeterinaryPartnerCreate,
    VeterinaryPartnerUpdate,
)
from pawguard.modules.portal.service import PortalService
from pawguard.modules.settings.models import SystemSetting
from pawguard.services.cache_service import CacheService


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
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        mock_session.execute.return_value = mock_result
        stats = await service.get_hero_stats()
        assert stats.total_rescued == 10
        assert stats.active_care_count == 10
        assert stats.successful_adoptions == 10
        assert stats.urgent_rescue_count == 10

    @pytest.mark.asyncio
    async def test_get_hero_stats_cache_hit_skips_db(self, mock_repo, mock_session):
        """A warm cache must short-circuit the aggregate queries entirely."""
        cache = AsyncMock(spec=CacheService)
        cache.get.return_value = {
            "total_rescued": 42,
            "active_care_count": 7,
            "successful_adoptions": 3,
            "urgent_rescue_count": 1,
        }
        svc = PortalService(mock_repo, mock_session, cache_service=cache)
        stats = await svc.get_hero_stats()
        assert stats.total_rescued == 42
        assert stats.active_care_count == 7
        assert stats.successful_adoptions == 3
        assert stats.urgent_rescue_count == 1
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_hero_stats_cache_miss_populates(self, mock_repo, mock_session):
        cache = AsyncMock(spec=CacheService)
        cache.get.return_value = None
        svc = PortalService(mock_repo, mock_session, cache_service=cache)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_session.execute.return_value = mock_result
        stats = await svc.get_hero_stats()
        assert stats.total_rescued == 5
        cache.set.assert_awaited_once()

    # ── Legal documents ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_legal_doc(self, service, mock_repo):
        mock_repo.get_legal_doc_by_slug.return_value = None
        doc_id = uuid.uuid4()
        mock_repo.create_legal_doc.return_value = LegalDocument(
            id=doc_id, slug="terms-of-service", title="Terms", body="Body",
            document_type=LegalDocumentType.TERMS, status=ContentStatus.DRAFT,
        )
        payload = LegalDocumentCreate(
            slug="terms-of-service", title="Terms", body="Body"
        )
        result = await service.create_legal_doc(payload)
        assert result.title == "Terms"

    @pytest.mark.asyncio
    async def test_create_legal_doc_purges_stats_cache(self, mock_repo, mock_session):
        """A legal-doc write must purge the cached hero/transparency stats so
        the public page reflects the change without waiting out the TTL."""
        cache = AsyncMock(spec=CacheService)
        svc = PortalService(mock_repo, mock_session, cache_service=cache)
        mock_repo.get_legal_doc_by_slug.return_value = None
        mock_repo.create_legal_doc.return_value = LegalDocument(
            id=uuid.uuid4(), slug="privacy", title="Privacy", body="B",
            document_type=LegalDocumentType.PRIVACY, status=ContentStatus.DRAFT,
        )
        await svc.create_legal_doc(
            LegalDocumentCreate(slug="privacy", title="Privacy", body="B")
        )
        deleted = {c.args[0] for c in cache.delete.await_args_list}
        assert deleted == {"hero_stats", "transparency_stats"}

    @pytest.mark.asyncio
    async def test_create_legal_doc_duplicate_slug(self, service, mock_repo):
        mock_repo.get_legal_doc_by_slug.return_value = LegalDocument(
            id=uuid.uuid4(), slug="terms", title="Existing", body="B",
            document_type=LegalDocumentType.OTHER, status=ContentStatus.DRAFT,
        )
        payload = LegalDocumentCreate(slug="terms", title="New", body="B")
        with pytest.raises(ConflictError, match="slug.*already exists"):
            await service.create_legal_doc(payload)

    @pytest.mark.asyncio
    async def test_update_legal_doc(self, service, mock_repo):
        doc_id = uuid.uuid4()
        doc = LegalDocument(
            id=doc_id, slug="terms", title="Old", body="B",
            document_type=LegalDocumentType.TERMS, status=ContentStatus.DRAFT,
        )
        mock_repo.get_legal_doc.return_value = doc
        payload = LegalDocumentUpdate(title="Updated")
        result = await service.update_legal_doc(doc_id, payload)
        assert result.title == "Updated"

    @pytest.mark.asyncio
    async def test_update_legal_doc_not_found(self, service, mock_repo):
        mock_repo.get_legal_doc.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_legal_doc(uuid.uuid4(), LegalDocumentUpdate())

    @pytest.mark.asyncio
    async def test_get_legal_doc_published_only(self, service, mock_repo):
        doc = LegalDocument(
            id=uuid.uuid4(), slug="privacy", title="Privacy", body="B",
            document_type=LegalDocumentType.PRIVACY, status=ContentStatus.PUBLISHED,
        )
        mock_repo.get_legal_doc_by_slug.return_value = doc
        result = await service.get_legal_doc_by_slug("privacy", published_only=True)
        assert result.title == "Privacy"

    @pytest.mark.asyncio
    async def test_get_legal_doc_hidden_when_draft(self, service, mock_repo):
        doc = LegalDocument(
            id=uuid.uuid4(), slug="terms", title="T", body="B",
            document_type=LegalDocumentType.OTHER, status=ContentStatus.DRAFT,
        )
        mock_repo.get_legal_doc_by_slug.return_value = doc
        with pytest.raises(NotFoundError):
            await service.get_legal_doc_by_slug("terms", published_only=True)

    @pytest.mark.asyncio
    async def test_list_legal_docs_paginated(self, service, mock_repo):
        doc = LegalDocument(
            id=uuid.uuid4(), slug="terms", title="T", body="B",
            document_type=LegalDocumentType.OTHER, status=ContentStatus.DRAFT,
        )
        mock_repo.count_legal_docs.return_value = 1
        mock_repo.list_legal_docs.return_value = [doc]
        docs, meta = await service.list_legal_docs_paginated()
        assert len(docs) == 1
        assert meta.total == 1

    @pytest.mark.asyncio
    async def test_soft_delete_legal_doc(self, service, mock_repo):
        doc_id = uuid.uuid4()
        mock_repo.get_legal_doc.return_value = LegalDocument(
            id=doc_id, slug="terms", title="T", body="B",
            document_type=LegalDocumentType.OTHER, status=ContentStatus.DRAFT,
        )
        mock_repo.soft_delete_legal_doc.return_value = None
        await service.soft_delete_legal_doc(doc_id)
        mock_repo.soft_delete_legal_doc.assert_called_once_with(doc_id)

    # ── Urgent alerts ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_urgent_alert(self, service, mock_repo):
        alert_id = uuid.uuid4()
        mock_repo.create_urgent_alert.return_value = UrgentAlert(
            id=alert_id, title="Flood", message="Roads flooded.",
            severity=AlertSeverity.WARNING, is_active=True,
        )
        payload = UrgentAlertCreate(title="Flood", message="Roads flooded.")
        result = await service.create_urgent_alert(payload)
        assert result.title == "Flood"

    @pytest.mark.asyncio
    async def test_update_urgent_alert_purges_stats_cache(self, mock_repo, mock_session):
        """An alert write must purge the cached aggregates too."""
        cache = AsyncMock(spec=CacheService)
        svc = PortalService(mock_repo, mock_session, cache_service=cache)
        mock_repo.get_urgent_alert.return_value = UrgentAlert(
            id=uuid.uuid4(), title="Flood", message="Old",
            severity=AlertSeverity.INFO, is_active=True,
        )
        await svc.update_urgent_alert(
            uuid.uuid4(), UrgentAlertUpdate(message="New")
        )
        deleted = {c.args[0] for c in cache.delete.await_args_list}
        assert deleted == {"hero_stats", "transparency_stats"}

    @pytest.mark.asyncio
    async def test_update_urgent_alert(self, service, mock_repo):
        alert_id = uuid.uuid4()
        alert = UrgentAlert(
            id=alert_id, title="Flood", message="Old",
            severity=AlertSeverity.INFO, is_active=True,
        )
        mock_repo.get_urgent_alert.return_value = alert
        payload = UrgentAlertUpdate(message="New")
        result = await service.update_urgent_alert(alert_id, payload)
        assert result.message == "New"

    @pytest.mark.asyncio
    async def test_update_urgent_alert_not_found(self, service, mock_repo):
        mock_repo.get_urgent_alert.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_urgent_alert(uuid.uuid4(), UrgentAlertUpdate())

    @pytest.mark.asyncio
    async def test_get_active_alerts(self, service, mock_repo):
        alert = UrgentAlert(
            id=uuid.uuid4(), title="Alert", message="M",
            severity=AlertSeverity.CRITICAL, is_active=True,
        )
        mock_repo.list_active_alerts.return_value = [alert]
        alerts = await service.get_active_alerts()
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_soft_delete_urgent_alert(self, service, mock_repo):
        alert_id = uuid.uuid4()
        mock_repo.get_urgent_alert.return_value = UrgentAlert(
            id=alert_id, title="A", message="M",
            severity=AlertSeverity.INFO, is_active=True,
        )
        mock_repo.soft_delete_urgent_alert.return_value = None
        await service.soft_delete_urgent_alert(alert_id)
        mock_repo.soft_delete_urgent_alert.assert_called_once_with(alert_id)

    # ── Transparency stats ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_transparency_stats(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        mock_session.execute.return_value = mock_result
        stats = await service.get_transparency_stats()
        assert stats.total_funds_raised == 10.0
        assert stats.total_donations == 10
        assert stats.total_rescues_completed == 10
        assert stats.successful_adoptions == 10
        assert stats.active_volunteers == 10
        assert stats.active_foster_homes == 10
        assert stats.veterinary_partners == 10
        assert stats.dogs_in_care == 10

    @pytest.mark.asyncio
    async def test_create_vet_purges_stats_cache(self, mock_repo, mock_session):
        """Vet-partner writes feed the transparency aggregate - purge it."""
        cache = AsyncMock(spec=CacheService)
        svc = PortalService(mock_repo, mock_session, cache_service=cache)
        mock_repo.create_vet.return_value = VeterinaryPartner(
            id=uuid.uuid4(), name="Vet", address="A", phone="+12345",
            is_emergency=False, is_active=True,
        )
        await svc.create_vet(
            VeterinaryPartnerCreate(name="Vet", address="A", phone="+12345")
        )
        deleted = {c.args[0] for c in cache.delete.await_args_list}
        assert deleted == {"hero_stats", "transparency_stats"}

    @pytest.mark.asyncio
    async def test_get_transparency_stats_cache_hit(self, mock_repo, mock_session):
        cache = AsyncMock(spec=CacheService)
        cache.get.return_value = {
            "total_funds_raised": 100.5,
            "total_donations": 12,
            "total_rescues_completed": 8,
            "successful_adoptions": 4,
            "active_volunteers": 20,
            "active_foster_homes": 5,
            "veterinary_partners": 3,
            "dogs_in_care": 15,
        }
        svc = PortalService(mock_repo, mock_session, cache_service=cache)
        stats = await svc.get_transparency_stats()
        assert stats.total_funds_raised == 100.5
        assert stats.total_donations == 12
        mock_session.execute.assert_not_called()
