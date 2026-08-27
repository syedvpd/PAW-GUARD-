"""Data access for the public portal CMS module."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting
from pawguard.modules.auth.models import User
from pawguard.modules.portal.models import (
    AlertSeverity,
    BlogPost,
    CmsPage,
    CmsPageVersion,
    CmsSection,
    ContactLocation,
    ContactMessage,
    ContentStatus,
    FAQEntry,
    LegalDocument,
    NewsletterSubscription,
    SuccessStory,
    UrgentAlert,
    VeterinaryPartner,
)
from pawguard.modules.settings.models import SystemSetting


class PortalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(
            func.lower(User.email) == email.strip().lower(),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_contact_message(self, message: ContactMessage) -> ContactMessage:
        self._session.add(message)
        await self._session.flush()
        return message

    async def get_newsletter_subscription(
        self, user_id: uuid.UUID
    ) -> NewsletterSubscription | None:
        stmt = select(NewsletterSubscription).where(NewsletterSubscription.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_newsletter_subscription(
        self, subscription: NewsletterSubscription
    ) -> NewsletterSubscription:
        self._session.add(subscription)
        await self._session.flush()
        return subscription

    # ── Success stories ─────────────────────────────────────────────────────

    async def create_story(self, story: SuccessStory) -> SuccessStory:
        self._session.add(story)
        await self._session.flush()
        await self._session.refresh(story)
        return story

    async def get_story(self, story_id: uuid.UUID) -> SuccessStory | None:
        stmt = select(SuccessStory).where(
            SuccessStory.id == story_id, SuccessStory.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_story_by_slug(self, slug: str) -> SuccessStory | None:
        stmt = select(SuccessStory).where(
            SuccessStory.slug == slug, SuccessStory.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_stories(
        self,
        *,
        status: ContentStatus | None = None,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count(SuccessStory.id)).where(SuccessStory.deleted_at.is_(None))
        if status:
            stmt = stmt.where(SuccessStory.status == status)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    SuccessStory.title.ilike(like),
                    SuccessStory.body.ilike(like),
                    SuccessStory.summary.ilike(like),
                )
            )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_stories(
        self,
        *,
        published_only: bool = False,
        page_params: PageParams | None = None,
        status: ContentStatus | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> Sequence[SuccessStory]:
        stmt = select(SuccessStory).where(SuccessStory.deleted_at.is_(None))
        if published_only:
            stmt = stmt.where(SuccessStory.status == ContentStatus.PUBLISHED)
        if status:
            stmt = stmt.where(SuccessStory.status == status)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    SuccessStory.title.ilike(like),
                    SuccessStory.body.ilike(like),
                    SuccessStory.summary.ilike(like),
                )
            )
        valid_sort = {
            "created_at",
            "updated_at",
            "published_at",
            "title",
            "status",
            "sort_order",
            "is_featured",
        }
        if sort:
            stmt = apply_sorting(stmt, sort, valid_sort, default_field="created_at")
        else:
            stmt = stmt.order_by(
                SuccessStory.is_featured.desc(),
                SuccessStory.sort_order.asc(),
                SuccessStory.published_at.desc().nullslast(),
                SuccessStory.created_at.desc(),
            )
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    # ── Blog posts ──────────────────────────────────────────────────────────

    async def create_blog(self, post: BlogPost) -> BlogPost:
        self._session.add(post)
        await self._session.flush()
        await self._session.refresh(post)
        return post

    async def get_blog_by_id(self, post_id: uuid.UUID) -> BlogPost | None:
        stmt = select(BlogPost).where(BlogPost.id == post_id, BlogPost.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_related_blogs(
        self,
        *,
        post_id: uuid.UUID,
        limit: int,
        published_only: bool = True,
        category: str | None = None,
    ) -> Sequence[BlogPost]:
        """Server-side related-blog lookup.

        Excludes the source post, prefers same-category matches, then falls
        back to the most recently published posts. ``limit`` is enforced at the
        query level so the response stays small (no full collection scan).
        """
        source = await self.get_blog_by_id(post_id)
        source_category = source.category if source is not None else None
        stmt = select(BlogPost).where(
            BlogPost.deleted_at.is_(None),
            BlogPost.id != post_id,
        )
        if published_only:
            stmt = stmt.where(BlogPost.status == ContentStatus.PUBLISHED)
        if category:
            stmt = stmt.where(BlogPost.category == category)
        if source_category:
            stmt = stmt.order_by(
                (BlogPost.category == source_category).desc(),
                BlogPost.published_at.desc().nullslast(),
                BlogPost.created_at.desc(),
            )
        else:
            stmt = stmt.order_by(
                BlogPost.published_at.desc().nullslast(),
                BlogPost.created_at.desc(),
            )
        stmt = stmt.limit(limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_blog_by_slug(self, slug: str) -> BlogPost | None:
        stmt = select(BlogPost).where(BlogPost.slug == slug, BlogPost.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_blogs(
        self,
        *,
        status: ContentStatus | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count(BlogPost.id)).where(BlogPost.deleted_at.is_(None))
        if status:
            stmt = stmt.where(BlogPost.status == status)
        if category:
            stmt = stmt.where(BlogPost.category == category)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    BlogPost.title.ilike(like),
                    BlogPost.body.ilike(like),
                    BlogPost.excerpt.ilike(like),
                    BlogPost.category.ilike(like),
                )
            )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_blogs(
        self,
        *,
        published_only: bool = False,
        page_params: PageParams | None = None,
        status: ContentStatus | None = None,
        category: str | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> Sequence[BlogPost]:
        stmt = select(BlogPost).where(BlogPost.deleted_at.is_(None))
        if published_only:
            stmt = stmt.where(BlogPost.status == ContentStatus.PUBLISHED)
        if status:
            stmt = stmt.where(BlogPost.status == status)
        if category:
            stmt = stmt.where(BlogPost.category == category)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    BlogPost.title.ilike(like),
                    BlogPost.body.ilike(like),
                    BlogPost.excerpt.ilike(like),
                    BlogPost.category.ilike(like),
                )
            )
        valid_sort = {"created_at", "updated_at", "published_at", "title", "category", "status"}
        if sort:
            stmt = apply_sorting(stmt, sort, valid_sort, default_field="created_at")
        else:
            stmt = stmt.order_by(
                BlogPost.published_at.desc().nullslast(), BlogPost.created_at.desc()
            )
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    # ── Veterinary partners ─────────────────────────────────────────────────

    async def create_vet(self, partner: VeterinaryPartner) -> VeterinaryPartner:
        self._session.add(partner)
        await self._session.flush()
        await self._session.refresh(partner)
        return partner

    async def get_vet(self, partner_id: uuid.UUID) -> VeterinaryPartner | None:
        stmt = select(VeterinaryPartner).where(
            VeterinaryPartner.id == partner_id, VeterinaryPartner.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_vets(self, *, active_only: bool, emergency_only: bool = False) -> int:
        stmt = select(func.count(VeterinaryPartner.id)).where(
            VeterinaryPartner.deleted_at.is_(None)
        )
        if active_only:
            stmt = stmt.where(VeterinaryPartner.is_active.is_(True))
        if emergency_only:
            stmt = stmt.where(VeterinaryPartner.is_emergency.is_(True))
        return (await self._session.execute(stmt)).scalar() or 0

    async def list_vets(
        self,
        *,
        active_only: bool,
        emergency_only: bool = False,
        page_params: PageParams | None = None,
    ) -> Sequence[VeterinaryPartner]:
        stmt = select(VeterinaryPartner).where(VeterinaryPartner.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(VeterinaryPartner.is_active.is_(True))
        if emergency_only:
            stmt = stmt.where(VeterinaryPartner.is_emergency.is_(True))
        stmt = stmt.order_by(VeterinaryPartner.name.asc())
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    # ── Contact locations ────────────────────────────────────────────────────

    async def create_contact(self, location: ContactLocation) -> ContactLocation:
        self._session.add(location)
        await self._session.flush()
        await self._session.refresh(location)
        return location

    async def get_contact(self, location_id: uuid.UUID) -> ContactLocation | None:
        stmt = select(ContactLocation).where(
            ContactLocation.id == location_id, ContactLocation.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_contacts(self) -> Sequence[ContactLocation]:
        stmt = (
            select(ContactLocation)
            .where(ContactLocation.deleted_at.is_(None))
            .order_by(ContactLocation.sort_order.asc(), ContactLocation.name.asc())
            .limit(50)
        )
        return (await self._session.execute(stmt)).scalars().all()

    # ── FAQ ─────────────────────────────────────────────────────────────────

    async def create_faq(self, entry: FAQEntry) -> FAQEntry:
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def get_faq(self, entry_id: uuid.UUID) -> FAQEntry | None:
        stmt = select(FAQEntry).where(FAQEntry.id == entry_id, FAQEntry.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_faqs(
        self,
        *,
        is_published: bool | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count(FAQEntry.id)).where(FAQEntry.deleted_at.is_(None))
        if is_published is not None:
            stmt = stmt.where(FAQEntry.is_published.is_(is_published))
        if category:
            stmt = stmt.where(FAQEntry.category == category)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    FAQEntry.question.ilike(like),
                    FAQEntry.answer.ilike(like),
                    FAQEntry.category.ilike(like),
                )
            )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_faqs(
        self,
        *,
        published_only: bool = False,
        page_params: PageParams | None = None,
        is_published: bool | None = None,
        category: str | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> Sequence[FAQEntry]:
        stmt = select(FAQEntry).where(FAQEntry.deleted_at.is_(None))
        if published_only:
            stmt = stmt.where(FAQEntry.is_published.is_(True))
        if is_published is not None:
            stmt = stmt.where(FAQEntry.is_published.is_(is_published))
        if category:
            stmt = stmt.where(FAQEntry.category == category)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    FAQEntry.question.ilike(like),
                    FAQEntry.answer.ilike(like),
                    FAQEntry.category.ilike(like),
                )
            )
        valid_sort = {"created_at", "sort_order", "category", "is_published"}
        if sort:
            stmt = apply_sorting(stmt, sort, valid_sort, default_field="sort_order")
        else:
            stmt = stmt.order_by(FAQEntry.sort_order.asc(), FAQEntry.created_at.asc())
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    # ── Settings ────────────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> SystemSetting | None:
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_settings(self) -> Sequence[SystemSetting]:
        stmt = select(SystemSetting).order_by(SystemSetting.key.asc())
        return (await self._session.execute(stmt)).scalars().all()

    async def upsert_setting(self, setting: SystemSetting) -> SystemSetting:
        self._session.add(setting)
        await self._session.flush()
        return setting

    # ── Soft delete ─────────────────────────────────────────────────────────

    async def soft_delete_story(self, story_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        stmt = select(SuccessStory).where(
            SuccessStory.id == story_id, SuccessStory.deleted_at.is_(None)
        )
        obj = (await self._session.execute(stmt)).scalar_one_or_none()
        if obj:
            obj.deleted_at = now

    async def soft_delete_blog(self, post_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        stmt = select(BlogPost).where(BlogPost.id == post_id, BlogPost.deleted_at.is_(None))
        obj = (await self._session.execute(stmt)).scalar_one_or_none()
        if obj:
            obj.deleted_at = now

    async def soft_delete_faq(self, entry_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        stmt = select(FAQEntry).where(FAQEntry.id == entry_id, FAQEntry.deleted_at.is_(None))
        obj = (await self._session.execute(stmt)).scalar_one_or_none()
        if obj:
            obj.deleted_at = now

    async def soft_delete_contact(self, location_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        stmt = select(ContactLocation).where(
            ContactLocation.id == location_id, ContactLocation.deleted_at.is_(None)
        )
        obj = (await self._session.execute(stmt)).scalar_one_or_none()
        if obj:
            obj.deleted_at = now

    async def soft_delete_vet(self, partner_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        stmt = select(VeterinaryPartner).where(
            VeterinaryPartner.id == partner_id, VeterinaryPartner.deleted_at.is_(None)
        )
        obj = (await self._session.execute(stmt)).scalar_one_or_none()
        if obj:
            obj.deleted_at = now

    # ── Legal documents ────────────────────────────────────────────────────

    async def create_legal_doc(self, doc: LegalDocument) -> LegalDocument:
        self._session.add(doc)
        await self._session.flush()
        return doc

    async def get_legal_doc(self, doc_id: uuid.UUID) -> LegalDocument | None:
        stmt = select(LegalDocument).where(
            LegalDocument.id == doc_id, LegalDocument.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_legal_doc_by_slug(self, slug: str) -> LegalDocument | None:
        stmt = select(LegalDocument).where(
            LegalDocument.slug == slug, LegalDocument.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_legal_docs(
        self,
        *,
        status: ContentStatus | None = None,
        document_type: str | None = None,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count(LegalDocument.id)).where(LegalDocument.deleted_at.is_(None))
        if status:
            stmt = stmt.where(LegalDocument.status == status)
        if document_type:
            stmt = stmt.where(LegalDocument.document_type == document_type)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    LegalDocument.title.ilike(like),
                    LegalDocument.body.ilike(like),
                    LegalDocument.slug.ilike(like),
                )
            )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_legal_docs(
        self,
        *,
        published_only: bool = False,
        page_params: PageParams | None = None,
        status: ContentStatus | None = None,
        document_type: str | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> Sequence[LegalDocument]:
        stmt = select(LegalDocument).where(LegalDocument.deleted_at.is_(None))
        if published_only:
            stmt = stmt.where(LegalDocument.status == ContentStatus.PUBLISHED)
        if status:
            stmt = stmt.where(LegalDocument.status == status)
        if document_type:
            stmt = stmt.where(LegalDocument.document_type == document_type)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    LegalDocument.title.ilike(like),
                    LegalDocument.body.ilike(like),
                    LegalDocument.slug.ilike(like),
                )
            )
        valid_sort = {"created_at", "updated_at", "published_at", "title", "version", "status"}
        if sort:
            stmt = apply_sorting(stmt, sort, valid_sort, default_field="created_at")
        else:
            stmt = stmt.order_by(
                LegalDocument.published_at.desc().nullslast(), LegalDocument.created_at.desc()
            )
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def soft_delete_legal_doc(self, doc_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        stmt = select(LegalDocument).where(
            LegalDocument.id == doc_id, LegalDocument.deleted_at.is_(None)
        )
        obj = (await self._session.execute(stmt)).scalar_one_or_none()
        if obj:
            obj.deleted_at = now

    # ── Urgent alerts ──────────────────────────────────────────────────────

    async def create_urgent_alert(self, alert: UrgentAlert) -> UrgentAlert:
        self._session.add(alert)
        await self._session.flush()
        return alert

    async def get_urgent_alert(self, alert_id: uuid.UUID) -> UrgentAlert | None:
        stmt = select(UrgentAlert).where(
            UrgentAlert.id == alert_id, UrgentAlert.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_urgent_alerts(
        self,
        *,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count(UrgentAlert.id)).where(UrgentAlert.deleted_at.is_(None))
        if is_active is not None:
            stmt = stmt.where(UrgentAlert.is_active.is_(is_active))
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    UrgentAlert.title.ilike(like),
                    UrgentAlert.message.ilike(like),
                )
            )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_urgent_alerts(
        self,
        *,
        page_params: PageParams | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> Sequence[UrgentAlert]:
        stmt = select(UrgentAlert).where(UrgentAlert.deleted_at.is_(None))
        if is_active is not None:
            stmt = stmt.where(UrgentAlert.is_active.is_(is_active))
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    UrgentAlert.title.ilike(like),
                    UrgentAlert.message.ilike(like),
                )
            )
        valid_sort = {"created_at", "updated_at", "severity", "sort_order", "is_active"}
        if sort:
            stmt = apply_sorting(stmt, sort, valid_sort, default_field="sort_order")
        else:
            stmt = stmt.order_by(UrgentAlert.sort_order.asc(), UrgentAlert.created_at.desc())
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    @staticmethod
    def _active_alert_filter(stmt: Any) -> Any:
        """Shared WHERE clause for active alerts inside their scheduled window."""
        now = datetime.now(UTC)
        return stmt.where(
            UrgentAlert.deleted_at.is_(None),
            UrgentAlert.is_active.is_(True),
            or_(UrgentAlert.starts_at.is_(None), UrgentAlert.starts_at <= now),
            or_(UrgentAlert.ends_at.is_(None), UrgentAlert.ends_at >= now),
        )

    async def count_active_alerts(self) -> int:
        stmt = self._active_alert_filter(select(func.count(UrgentAlert.id)))
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_active_alerts(
        self, *, page_params: PageParams | None = None
    ) -> Sequence[UrgentAlert]:
        """Active alerts inside their scheduled window (if any), highest
        severity first, then sort order. Optional pagination support."""
        severity_order = case(
            (UrgentAlert.severity == AlertSeverity.CRITICAL, 0),
            (UrgentAlert.severity == AlertSeverity.WARNING, 1),
            else_=2,
        )
        stmt = (
            select(UrgentAlert)
            .order_by(
                severity_order,
                UrgentAlert.sort_order.asc(),
                UrgentAlert.created_at.desc(),
            )
        )
        stmt = self._active_alert_filter(stmt)
        if page_params is not None:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def soft_delete_urgent_alert(self, alert_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        stmt = select(UrgentAlert).where(
            UrgentAlert.id == alert_id, UrgentAlert.deleted_at.is_(None)
        )
        obj = (await self._session.execute(stmt)).scalar_one_or_none()
        if obj:
            obj.deleted_at = now

    # ── Bulk operations ─────────────────────────────────────────────────────

    async def bulk_soft_delete_stories(self, ids: list[uuid.UUID]) -> int:
        now = datetime.now(UTC)
        stmt = select(SuccessStory).where(
            SuccessStory.id.in_(ids), SuccessStory.deleted_at.is_(None)
        )
        objs = (await self._session.execute(stmt)).scalars().all()
        for o in objs:
            o.deleted_at = now
        return len(objs)

    async def bulk_soft_delete_blogs(self, ids: list[uuid.UUID]) -> int:
        now = datetime.now(UTC)
        stmt = select(BlogPost).where(BlogPost.id.in_(ids), BlogPost.deleted_at.is_(None))
        objs = (await self._session.execute(stmt)).scalars().all()
        for o in objs:
            o.deleted_at = now
        return len(objs)

    async def bulk_soft_delete_faqs(self, ids: list[uuid.UUID]) -> int:
        now = datetime.now(UTC)
        stmt = select(FAQEntry).where(FAQEntry.id.in_(ids), FAQEntry.deleted_at.is_(None))
        objs = (await self._session.execute(stmt)).scalars().all()
        for o in objs:
            o.deleted_at = now
        return len(objs)

    async def bulk_update_story_status(self, ids: list[uuid.UUID], status: ContentStatus) -> int:
        stmt = select(SuccessStory).where(
            SuccessStory.id.in_(ids), SuccessStory.deleted_at.is_(None)
        )
        objs = (await self._session.execute(stmt)).scalars().all()
        for o in objs:
            o.status = status
            if status == ContentStatus.PUBLISHED and o.published_at is None:
                o.published_at = datetime.now(UTC)
            if status == ContentStatus.DRAFT:
                o.published_at = None
        return len(objs)

    async def bulk_update_blog_status(self, ids: list[uuid.UUID], status: ContentStatus) -> int:
        stmt = select(BlogPost).where(BlogPost.id.in_(ids), BlogPost.deleted_at.is_(None))
        objs = (await self._session.execute(stmt)).scalars().all()
        for o in objs:
            o.status = status
            if status == ContentStatus.PUBLISHED and o.published_at is None:
                o.published_at = datetime.now(UTC)
            if status == ContentStatus.DRAFT:
                o.published_at = None
        return len(objs)

    async def bulk_update_faq_status(self, ids: list[uuid.UUID], is_published: bool) -> int:
        stmt = select(FAQEntry).where(FAQEntry.id.in_(ids), FAQEntry.deleted_at.is_(None))
        objs = (await self._session.execute(stmt)).scalars().all()
        for o in objs:
            o.is_published = is_published
        return len(objs)

    # ── Dynamic CMS Pages & Content ──────────────────────────────────────────

    async def get_cms_page_by_slug(self, slug: str) -> CmsPage | None:
        stmt = (
            select(CmsPage)
            .options(
                selectinload(CmsPage.sections).selectinload(CmsSection.fields),
                selectinload(CmsPage.versions),
            )
            .where(CmsPage.slug == slug, CmsPage.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_cms_pages(self) -> Sequence[CmsPage]:
        stmt = (
            select(CmsPage)
            .options(selectinload(CmsPage.sections).selectinload(CmsSection.fields))
            .where(CmsPage.deleted_at.is_(None))
            .order_by(CmsPage.name)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_cms_page(self, page: CmsPage) -> CmsPage:
        self._session.add(page)
        await self._session.flush()
        return page

    async def save_cms_page(self) -> None:
        await self._session.flush()

    async def create_cms_page_version(self, version: CmsPageVersion) -> CmsPageVersion:
        self._session.add(version)
        await self._session.flush()
        return version
