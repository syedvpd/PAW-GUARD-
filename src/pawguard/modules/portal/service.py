"""PortalService: owns CMS content and public portal business behaviour (RULE-003)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginationMeta
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.auth.service import RequestContext
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.donation.models import Donation, DonationStatus, DonorProfile
from pawguard.modules.foster.models import FosterProfile, FosterStatus
from pawguard.modules.lost_found.models import FoundReport, LostReport
from pawguard.modules.portal.models import (
    BlogPost,
    CmsContentField,
    CmsPage,
    CmsPageVersion,
    CmsSection,
    ContactLocation,
    ContentStatus,
    FAQEntry,
    LegalDocument,
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
    PublicHeroStats,
    SuccessStoryCreate,
    SuccessStoryUpdate,
    TransparencyStats,
    UrgentAlertCreate,
    UrgentAlertUpdate,
    UserDashboardSummary,
    CmsPageResponse,
    CmsPageUpdate,
    PublicCmsPageResponse,
    VeterinaryPartnerCreate,
    VeterinaryPartnerUpdate,
)
from pawguard.modules.rescue.models import (
    RescueRequest,
    RescueSeverity,
    RescueStatus,
)
from pawguard.modules.settings.models import SystemSetting
from pawguard.modules.volunteer.models import VolunteerProfile, VolunteerStatus
from pawguard.services.audit_service import AuditService
from pawguard.services.cache_service import CacheService

# Public aggregate stats are expensive to compute (multiple count/sum scans)
# and change slowly; cache them briefly to keep the anonymous landing page
# cheap. The TTL is a safety net for cross-module data (dogs, donations,
# rescues); CMS content changes within this module purge the keys immediately
# via _invalidate_stats_cache(). The CacheService already namespaces with
# "portal", so bare keys are used here.
HERO_STATS_CACHE_KEY = "hero_stats"
TRANSPARENCY_STATS_CACHE_KEY = "transparency_stats"
PUBLIC_STATS_CACHE_TTL_SECONDS = 300


class PortalService:
    def __init__(
        self,
        repository: PortalRepository,
        session: AsyncSession,
        audit_service: AuditService | None = None,
        cache_service: CacheService | None = None,
    ) -> None:
        self._repo = repository
        self._session = session
        self._audit = audit_service
        self._cache = cache_service

    def _apply_publish(
        self,
        status: ContentStatus,
        entity: SuccessStory | BlogPost | LegalDocument,
    ) -> None:
        if status == ContentStatus.PUBLISHED and entity.published_at is None:
            entity.published_at = datetime.now(UTC)
        if status == ContentStatus.DRAFT:
            entity.published_at = None

    async def _invalidate_stats_cache(self) -> None:
        """Purge cached public aggregates after a CMS write so the landing
        page reflects the change immediately instead of waiting out the TTL.
        No-op when caching is disabled (Redis unavailable)."""
        if self._cache is None:
            return
        await self._cache.delete(HERO_STATS_CACHE_KEY)
        await self._cache.delete(TRANSPARENCY_STATS_CACHE_KEY)

    # ── Success stories ──────────────────────────────────────────────────────

    async def create_story(
        self,
        payload: SuccessStoryCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> SuccessStory:
        story = SuccessStory(**payload.model_dump())
        self._apply_publish(story.status, story)
        return await self._repo.create_story(story)

    async def update_story(
        self,
        story_id: uuid.UUID,
        payload: SuccessStoryUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> SuccessStory:
        story = await self._repo.get_story(story_id)
        if story is None:
            raise NotFoundError("Success story not found.")
        for field, value in payload.model_dump(
            exclude_unset=True
        ).items():
            setattr(story, field, value)
        if payload.status is not None:
            self._apply_publish(payload.status, story)
        await self._session.flush()
        # updated_at has onupdate=func.now() (server-computed) - after
        # flush() it's expired, and reading it during response
        # serialization triggers an implicit refresh that's unsafe outside
        # an explicit awaited context on an AsyncSession (MissingGreenlet).
        await self._session.refresh(story)
        return story

    async def get_story(
        self,
        story_id: uuid.UUID,
        *,
        published_only: bool,
    ) -> SuccessStory:
        story = await self._repo.get_story(story_id)
        if story is None or (
            published_only
            and story.status != ContentStatus.PUBLISHED
        ):
            raise NotFoundError("Success story not found.")
        return story

    async def list_stories(
        self,
        *,
        published_only: bool,
    ) -> list[SuccessStory]:
        return list(
            await self._repo.list_stories(
                published_only=published_only
            )
        )

    async def list_stories_paginated(
        self,
        *,
        page_params: PageParams | None = None,
        status: ContentStatus | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> tuple[list[SuccessStory], PaginationMeta]:
        total = await self._repo.count_stories(
            status=status, search=search
        )
        stories = await self._repo.list_stories(
            page_params=page_params,
            status=status,
            search=search,
            sort=sort,
        )
        meta = build_pagination_meta(
            total=total, params=page_params or PageParams()
        )
        return list(stories), meta

    # ── Blog posts ───────────────────────────────────────────────────────────

    async def create_blog(
        self,
        payload: BlogPostCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> BlogPost:
        existing = await self._repo.get_blog_by_slug(
            payload.slug
        )
        if existing is not None:
            raise ConflictError(
                f"Blog slug '{payload.slug}' already exists."
            )
        post = BlogPost(**payload.model_dump())
        self._apply_publish(post.status, post)
        result = await self._repo.create_blog(post)
        await self._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=(
                    AuthAuditEventType.PORTAL_POST_CREATED
                ),
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"post_id": str(result.id)},
            )
        return result

    async def update_blog(
        self,
        post_id: uuid.UUID,
        payload: BlogPostUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> BlogPost:
        post = await self._repo.get_blog_by_id(post_id)
        if post is None:
            raise NotFoundError("Blog post not found.")
        slug_taken = (
            payload.slug
            and payload.slug != post.slug
            and await self._repo.get_blog_by_slug(
                payload.slug
            )
            is not None
        )
        if slug_taken:
            raise ConflictError(
                f"Blog slug '{payload.slug}' already exists."
            )
        for field, value in payload.model_dump(
            exclude_unset=True
        ).items():
            setattr(post, field, value)
        if payload.status is not None:
            self._apply_publish(payload.status, post)
        await self._session.flush()
        await self._session.refresh(post)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=(
                    AuthAuditEventType.PORTAL_POST_UPDATED
                ),
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"post_id": str(post_id)},
            )
        return post

    async def get_blog(
        self,
        post_id: uuid.UUID,
        *,
        published_only: bool,
    ) -> BlogPost:
        post = await self._repo.get_blog_by_id(post_id)
        if post is None or (
            published_only
            and post.status != ContentStatus.PUBLISHED
        ):
            raise NotFoundError("Blog post not found.")
        return post

    async def get_blog_by_slug(
        self,
        slug: str,
        *,
        published_only: bool,
    ) -> BlogPost:
        post = await self._repo.get_blog_by_slug(slug)
        if post is None or (
            published_only
            and post.status != ContentStatus.PUBLISHED
        ):
            raise NotFoundError("Blog post not found.")
        return post

    async def list_blogs(
        self,
        *,
        published_only: bool,
        category: str | None = None,
    ) -> list[BlogPost]:
        return list(
            await self._repo.list_blogs(
                published_only=published_only,
                category=category,
            )
        )

    async def list_blogs_paginated(
        self,
        *,
        page_params: PageParams | None = None,
        status: ContentStatus | None = None,
        category: str | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> tuple[list[BlogPost], PaginationMeta]:
        total = await self._repo.count_blogs(
            status=status,
            category=category,
            search=search,
        )
        blogs = await self._repo.list_blogs(
            page_params=page_params,
            status=status,
            category=category,
            search=search,
            sort=sort,
        )
        meta = build_pagination_meta(
            total=total, params=page_params or PageParams()
        )
        return list(blogs), meta

    # ── Veterinary partners ──────────────────────────────────────────────────

    async def create_vet(
        self,
        payload: VeterinaryPartnerCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> VeterinaryPartner:
        result = await self._repo.create_vet(
            VeterinaryPartner(**payload.model_dump())
        )
        await self._session.flush()
        # veterinary_partners feeds the transparency aggregate - purge it.
        await self._invalidate_stats_cache()
        return result

    async def update_vet(
        self,
        partner_id: uuid.UUID,
        payload: VeterinaryPartnerUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> VeterinaryPartner:
        partner = await self._repo.get_vet(partner_id)
        if partner is None:
            raise NotFoundError(
                "Veterinary partner not found."
            )
        for field, value in payload.model_dump(
            exclude_unset=True
        ).items():
            setattr(partner, field, value)
        await self._session.flush()
        await self._session.refresh(partner)
        # veterinary_partners feeds the transparency aggregate - purge it.
        await self._invalidate_stats_cache()
        return partner

    async def list_vets(
        self,
        *,
        active_only: bool,
        emergency_only: bool = False,
    ) -> list[VeterinaryPartner]:
        return list(
            await self._repo.list_vets(
                active_only=active_only,
                emergency_only=emergency_only,
            )
        )

    # ── Contact locations ────────────────────────────────────────────────────

    async def create_contact(
        self,
        payload: ContactLocationCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ContactLocation:
        return await self._repo.create_contact(
            ContactLocation(**payload.model_dump())
        )

    async def update_contact(
        self,
        location_id: uuid.UUID,
        payload: ContactLocationUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ContactLocation:
        location = await self._repo.get_contact(location_id)
        if location is None:
            raise NotFoundError(
                "Contact location not found."
            )
        for field, value in payload.model_dump(
            exclude_unset=True
        ).items():
            setattr(location, field, value)
        await self._session.flush()
        await self._session.refresh(location)
        return location

    async def list_contacts(self) -> list[ContactLocation]:
        return list(await self._repo.list_contacts())

    # ── FAQ ────────────────────────────────────────────────────────────────────

    async def create_faq(
        self,
        payload: FAQEntryCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FAQEntry:
        return await self._repo.create_faq(
            FAQEntry(**payload.model_dump())
        )

    async def update_faq(
        self,
        entry_id: uuid.UUID,
        payload: FAQEntryUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FAQEntry:
        entry = await self._repo.get_faq(entry_id)
        if entry is None:
            raise NotFoundError("FAQ entry not found.")
        for field, value in payload.model_dump(
            exclude_unset=True
        ).items():
            setattr(entry, field, value)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def list_faqs(
        self,
        *,
        published_only: bool,
        category: str | None = None,
    ) -> list[FAQEntry]:
        return list(
            await self._repo.list_faqs(
                published_only=published_only,
                category=category,
            )
        )

    async def list_faqs_paginated(
        self,
        *,
        page_params: PageParams | None = None,
        is_published: bool | None = None,
        category: str | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> tuple[list[FAQEntry], PaginationMeta]:
        total = await self._repo.count_faqs(
            is_published=is_published,
            category=category,
            search=search,
        )
        faqs = await self._repo.list_faqs(
            page_params=page_params,
            is_published=is_published,
            category=category,
            search=search,
            sort=sort,
        )
        meta = build_pagination_meta(
            total=total, params=page_params or PageParams()
        )
        return list(faqs), meta

    # ── Soft delete ─────────────────────────────────────────────────────────

    async def soft_delete_story(
        self,
        story_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        story = await self._repo.get_story(story_id)
        if story is None:
            raise NotFoundError("Success story not found.")
        await self._repo.soft_delete_story(story_id)

    async def soft_delete_blog(
        self,
        post_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        post = await self._repo.get_blog_by_id(post_id)
        if post is None:
            raise NotFoundError("Blog post not found.")
        await self._repo.soft_delete_blog(post_id)
        await self._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=(
                    AuthAuditEventType.PORTAL_POST_DELETED
                ),
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"post_id": str(post_id)},
            )

    async def soft_delete_faq(
        self,
        entry_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        entry = await self._repo.get_faq(entry_id)
        if entry is None:
            raise NotFoundError("FAQ entry not found.")
        await self._repo.soft_delete_faq(entry_id)

    # ── Bulk operations ─────────────────────────────────────────────────────

    async def bulk_delete_stories(
        self,
        ids: list[uuid.UUID],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        return await self._repo.bulk_soft_delete_stories(ids)

    async def bulk_delete_blogs(
        self,
        ids: list[uuid.UUID],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_soft_delete_blogs(ids)
        await self._session.flush()
        if self._audit and actor_id:
            post_ids = [str(i) for i in ids]
            await self._audit.record(
                event_type=(
                    AuthAuditEventType.PORTAL_POST_DELETED
                ),
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "post_ids": post_ids,
                    "count": count,
                },
            )
        return count

    async def bulk_delete_faqs(
        self,
        ids: list[uuid.UUID],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_soft_delete_faqs(ids)
        if self._audit and actor_id:
            faq_ids = [str(i) for i in ids]
            await self._audit.record(
                event_type=(
                    AuthAuditEventType.PORTAL_POST_DELETED
                ),
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "faq_ids": faq_ids,
                    "count": count,
                },
            )
        return count

    async def bulk_update_story_status(
        self,
        ids: list[uuid.UUID],
        status: ContentStatus,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        return await self._repo.bulk_update_story_status(
            ids, status
        )

    async def bulk_update_blog_status(
        self,
        ids: list[uuid.UUID],
        status: ContentStatus,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_update_blog_status(
            ids, status
        )
        if self._audit and actor_id:
            post_ids = [str(i) for i in ids]
            await self._audit.record(
                event_type=(
                    AuthAuditEventType.PORTAL_POST_UPDATED
                ),
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "post_ids": post_ids,
                    "status": status.value,
                    "count": count,
                },
            )
        return count

    async def bulk_update_faq_status(
        self,
        ids: list[uuid.UUID],
        is_published: bool,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_update_faq_status(
            ids, is_published
        )
        if self._audit and actor_id:
            faq_ids = [str(i) for i in ids]
            await self._audit.record(
                event_type=(
                    AuthAuditEventType.PORTAL_POST_UPDATED
                ),
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "faq_ids": faq_ids,
                    "is_published": is_published,
                    "count": count,
                },
            )
        return count

    # ── Settings ─────────────────────────────────────────────────────────────

    async def upsert_setting(
        self,
        key: str,
        value: str,
        description: str | None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> SystemSetting:
        existing = await self._repo.get_setting(key)
        if existing is None:
            return await self._repo.upsert_setting(
                SystemSetting(
                    key=key,
                    value=value,
                    description=description,
                )
            )
        existing.value = value
        if description is not None:
            existing.description = description
        await self._session.flush()
        await self._session.refresh(existing)
        return existing

    async def get_setting(self, key: str) -> SystemSetting:
        setting = await self._repo.get_setting(key)
        if setting is None:
            raise NotFoundError(
                f"Setting '{key}' not found."
            )
        return setting

    async def list_settings(self) -> list[SystemSetting]:
        return list(await self._repo.list_settings())

    # ── Public hero stats ────────────────────────────────────────────────────

    async def get_hero_stats(self) -> PublicHeroStats:
        if self._cache is not None:
            cached = await self._cache.get(HERO_STATS_CACHE_KEY)
            if cached is not None:
                return PublicHeroStats(**cached)

        total_rescued = (
            await self._session.execute(
                select(func.count())
                .select_from(DogProfile)
                .where(
                    DogProfile.deleted_at.is_(None)
                )
            )
        ).scalar_one()
        active_care = (
            await self._session.execute(
                select(func.count())
                .select_from(DogProfile)
                .where(
                    DogProfile.deleted_at.is_(None),
                    DogProfile.status.in_(
                        [
                            DogStatus.RESCUED,
                            DogStatus.SHELTER,
                            DogStatus.FOSTERED,
                            DogStatus.CLINIC,
                        ]
                    ),
                )
            )
        ).scalar_one()
        adoptions = (
            await self._session.execute(
                select(func.count())
                .select_from(AdoptionApplication)
                .where(
                    AdoptionApplication.status
                    == AdoptionStatus.COMPLETED,
                    AdoptionApplication.deleted_at.is_(
                        None
                    ),
                )
            )
        ).scalar_one()
        # PRR 3.1.1 urgent-alert banner: CRITICAL/HIGH severity cases still in
        # the intake pipeline, plus anything the coordinators explicitly
        # flagged urgent for community assistance / foster placement.
        urgent = (
            await self._session.execute(
                select(func.count())
                .select_from(RescueRequest)
                .where(
                    RescueRequest.status.in_(
                        [
                            RescueStatus.REPORTED,
                            RescueStatus.VERIFIED,
                        ]
                    ),
                    RescueRequest.deleted_at.is_(None),
                    or_(
                        RescueRequest.severity.in_(
                            [RescueSeverity.CRITICAL, RescueSeverity.HIGH]
                        ),
                        RescueRequest.is_urgent.is_(True),
                    ),
                )
            )
        ).scalar_one()
        stats = PublicHeroStats(
            total_rescued=total_rescued,
            active_care_count=active_care,
            successful_adoptions=adoptions,
            urgent_rescue_count=urgent,
        )
        if self._cache is not None:
            await self._cache.set(
                HERO_STATS_CACHE_KEY,
                stats.model_dump(),
                ttl_seconds=PUBLIC_STATS_CACHE_TTL_SECONDS,
            )
        return stats

    # ── Transparency stats ──────────────────────────────────────────────────

    async def get_transparency_stats(self) -> TransparencyStats:
        """Public impact metrics for the transparency page (PRR §6.1)."""
        if self._cache is not None:
            cached = await self._cache.get(TRANSPARENCY_STATS_CACHE_KEY)
            if cached is not None:
                return TransparencyStats(**cached)

        funds_raised = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(Donation.amount), 0)
                ).where(Donation.status == DonationStatus.SUCCESS)
            )
        ).scalar_one()
        donations = (
            await self._session.execute(
                select(func.count())
                .select_from(Donation)
                .where(Donation.status == DonationStatus.SUCCESS)
            )
        ).scalar_one()
        rescues = (
            await self._session.execute(
                select(func.count())
                .select_from(RescueRequest)
                .where(
                    RescueRequest.status.in_(
                        [RescueStatus.RESCUED, RescueStatus.ADMITTED]
                    ),
                    RescueRequest.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        adoptions = (
            await self._session.execute(
                select(func.count())
                .select_from(AdoptionApplication)
                .where(
                    AdoptionApplication.status == AdoptionStatus.COMPLETED,
                    AdoptionApplication.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        volunteers = (
            await self._session.execute(
                select(func.count())
                .select_from(VolunteerProfile)
                .where(
                    VolunteerProfile.status.in_(
                        [
                            VolunteerStatus.ONBOARDED,
                            VolunteerStatus.ACTIVE,
                        ]
                    ),
                    VolunteerProfile.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        foster_homes = (
            await self._session.execute(
                select(func.count())
                .select_from(FosterProfile)
                .where(
                    FosterProfile.status == FosterStatus.APPROVED,
                    FosterProfile.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        vets = (
            await self._session.execute(
                select(func.count())
                .select_from(VeterinaryPartner)
                .where(
                    VeterinaryPartner.is_active.is_(True),
                    VeterinaryPartner.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        dogs_in_care = (
            await self._session.execute(
                select(func.count())
                .select_from(DogProfile)
                .where(
                    DogProfile.deleted_at.is_(None),
                    DogProfile.status.in_(
                        [
                            DogStatus.RESCUED,
                            DogStatus.SHELTER,
                            DogStatus.FOSTERED,
                            DogStatus.CLINIC,
                        ]
                    ),
                )
            )
        ).scalar_one()

        stats = TransparencyStats(
            total_funds_raised=float(funds_raised),
            total_donations=donations,
            total_rescues_completed=rescues,
            successful_adoptions=adoptions,
            active_volunteers=volunteers,
            active_foster_homes=foster_homes,
            veterinary_partners=vets,
            dogs_in_care=dogs_in_care,
        )
        if self._cache is not None:
            await self._cache.set(
                TRANSPARENCY_STATS_CACHE_KEY,
                stats.model_dump(),
                ttl_seconds=PUBLIC_STATS_CACHE_TTL_SECONDS,
            )
        return stats

    # ── Legal documents ─────────────────────────────────────────────────────

    async def create_legal_doc(
        self,
        payload: LegalDocumentCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> LegalDocument:
        existing = await self._repo.get_legal_doc_by_slug(payload.slug)
        if existing is not None:
            raise ConflictError(
                f"Legal document slug '{payload.slug}' already exists."
            )
        doc = LegalDocument(**payload.model_dump())
        self._apply_publish(doc.status, doc)
        result = await self._repo.create_legal_doc(doc)
        await self._session.flush()
        await self._invalidate_stats_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.PORTAL_POST_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"legal_doc_id": str(result.id)},
            )
        return result

    async def update_legal_doc(
        self,
        doc_id: uuid.UUID,
        payload: LegalDocumentUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> LegalDocument:
        doc = await self._repo.get_legal_doc(doc_id)
        if doc is None:
            raise NotFoundError("Legal document not found.")
        slug_taken = (
            payload.slug
            and payload.slug != doc.slug
            and await self._repo.get_legal_doc_by_slug(payload.slug)
            is not None
        )
        if slug_taken:
            raise ConflictError(
                f"Legal document slug '{payload.slug}' already exists."
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(doc, field, value)
        if payload.status is not None:
            self._apply_publish(payload.status, doc)
        await self._session.flush()
        await self._session.refresh(doc)
        await self._invalidate_stats_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.PORTAL_POST_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"legal_doc_id": str(doc_id)},
            )
        return doc

    async def get_legal_doc_by_slug(
        self,
        slug: str,
        *,
        published_only: bool,
    ) -> LegalDocument:
        doc = await self._repo.get_legal_doc_by_slug(slug)
        if doc is None or (
            published_only and doc.status != ContentStatus.PUBLISHED
        ):
            raise NotFoundError("Legal document not found.")
        return doc

    async def list_legal_docs(
        self,
        *,
        published_only: bool,
    ) -> list[LegalDocument]:
        return list(
            await self._repo.list_legal_docs(published_only=published_only)
        )

    async def list_legal_docs_paginated(
        self,
        *,
        page_params: PageParams | None = None,
        status: ContentStatus | None = None,
        document_type: str | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> tuple[list[LegalDocument], PaginationMeta]:
        total = await self._repo.count_legal_docs(
            status=status,
            document_type=document_type,
            search=search,
        )
        docs = await self._repo.list_legal_docs(
            page_params=page_params,
            status=status,
            document_type=document_type,
            search=search,
            sort=sort,
        )
        meta = build_pagination_meta(
            total=total, params=page_params or PageParams()
        )
        return list(docs), meta

    async def soft_delete_legal_doc(
        self,
        doc_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        doc = await self._repo.get_legal_doc(doc_id)
        if doc is None:
            raise NotFoundError("Legal document not found.")
        await self._repo.soft_delete_legal_doc(doc_id)
        await self._session.flush()
        await self._invalidate_stats_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.PORTAL_POST_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"legal_doc_id": str(doc_id)},
            )

    # ── Urgent alerts ───────────────────────────────────────────────────────

    async def create_urgent_alert(
        self,
        payload: UrgentAlertCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> UrgentAlert:
        alert = UrgentAlert(**payload.model_dump())
        result = await self._repo.create_urgent_alert(alert)
        await self._session.flush()
        await self._invalidate_stats_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.PORTAL_POST_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"urgent_alert_id": str(result.id)},
            )
        return result

    async def update_urgent_alert(
        self,
        alert_id: uuid.UUID,
        payload: UrgentAlertUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> UrgentAlert:
        alert = await self._repo.get_urgent_alert(alert_id)
        if alert is None:
            raise NotFoundError("Urgent alert not found.")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(alert, field, value)
        await self._session.flush()
        await self._session.refresh(alert)
        await self._invalidate_stats_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.PORTAL_POST_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"urgent_alert_id": str(alert_id)},
            )
        return alert

    async def get_active_alerts(self) -> list[UrgentAlert]:
        return list(await self._repo.list_active_alerts())

    async def list_urgent_alerts_paginated(
        self,
        *,
        page_params: PageParams | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> tuple[list[UrgentAlert], PaginationMeta]:
        total = await self._repo.count_urgent_alerts(
            is_active=is_active,
            search=search,
        )
        alerts = await self._repo.list_urgent_alerts(
            page_params=page_params,
            is_active=is_active,
            search=search,
            sort=sort,
        )
        meta = build_pagination_meta(
            total=total, params=page_params or PageParams()
        )
        return list(alerts), meta

    async def soft_delete_urgent_alert(
        self,
        alert_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        alert = await self._repo.get_urgent_alert(alert_id)
        if alert is None:
            raise NotFoundError("Urgent alert not found.")
        await self._repo.soft_delete_urgent_alert(alert_id)
        await self._session.flush()
        await self._invalidate_stats_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.PORTAL_POST_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"urgent_alert_id": str(alert_id)},
            )

    # ── User dashboard ───────────────────────────────────────────────────────

    async def get_user_dashboard(
        self,
        user_id: uuid.UUID,
        user_email: str,
    ) -> UserDashboardSummary:
        adoptions = (
            await self._session.execute(
                select(AdoptionApplication).where(
                    AdoptionApplication.adopter_id
                    == user_id,
                    AdoptionApplication.deleted_at.is_(
                        None
                    ),
                )
            )
        ).scalars().all()

        volunteer = (
            await self._session.execute(
                select(VolunteerProfile).where(
                    VolunteerProfile.user_id == user_id
                )
            )
        ).scalar_one_or_none()

        foster = (
            await self._session.execute(
                select(FosterProfile).where(
                    FosterProfile.user_id == user_id
                )
            )
        ).scalar_one_or_none()

        donations = (
            await self._session.execute(
                select(Donation)
                .join(
                    DonorProfile,
                    Donation.donor_id == DonorProfile.id,
                )
                .where(
                    DonorProfile.user_id == user_id
                )
            )
        ).scalars().all()

        rescues = (
            await self._session.execute(
                select(RescueRequest).where(
                    RescueRequest.reporter_email
                    == user_email.lower(),
                    RescueRequest.deleted_at.is_(None),
                )
            )
        ).scalars().all()

        lost_reports = (
            await self._session.execute(
                select(LostReport).where(
                    LostReport.user_id == user_id
                )
            )
        ).scalars().all()
        found_reports = (
            await self._session.execute(
                select(FoundReport).where(
                    FoundReport.user_id == user_id
                )
            )
        ).scalars().all()

        return UserDashboardSummary(
            rescue_cases=[
                self._serialize_rescue(r) for r in rescues
            ],
            adoption_applications=[
                self._serialize_adoption(a) for a in adoptions
            ],
            volunteer_profile=(
                self._serialize_volunteer(volunteer)
                if volunteer
                else None
            ),
            foster_profile=(
                self._serialize_foster(foster)
                if foster
                else None
            ),
            donations=[
                self._serialize_donation(d) for d in donations
            ],
            lost_found_reports=[
                *[
                    self._serialize_lost(lr)
                    for lr in lost_reports
                ],
                *[
                    self._serialize_found(f)
                    for f in found_reports
                ],
            ],
        )

    @staticmethod
    def _serialize_rescue(r: RescueRequest) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "ticket_number": r.ticket_number,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }

    @staticmethod
    def _serialize_adoption(
        a: AdoptionApplication,
    ) -> dict[str, Any]:
        return {
            "id": str(a.id),
            "dog_id": str(a.dog_id),
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }

    @staticmethod
    def _serialize_volunteer(
        v: VolunteerProfile,
    ) -> dict[str, Any]:
        return {
            "id": str(v.id),
            "status": v.status,
            "skills": v.skills,
        }

    @staticmethod
    def _serialize_foster(
        f: FosterProfile,
    ) -> dict[str, Any]:
        return {
            "id": str(f.id),
            "status": f.status,
            "max_capacity": f.max_capacity,
        }

    @staticmethod
    def _serialize_donation(
        d: Donation,
    ) -> dict[str, Any]:
        return {
            "id": str(d.id),
            "amount": float(d.amount),
            "status": d.status,
            "created_at": d.created_at.isoformat(),
        }

    @staticmethod
    def _serialize_lost(lr: LostReport) -> dict[str, Any]:
        return {
            "id": str(lr.id),
            "type": "lost",
            "pet_name": lr.pet_name,
            "status": lr.status,
        }

    @staticmethod
    def _serialize_found(f: FoundReport) -> dict[str, Any]:
        return {
            "id": str(f.id),
            "type": "found",
            "breed_observed": f.breed_observed,
            "status": f.status,
        }

    # ── Dynamic CMS Pages ───────────────────────────────────────────────────

    async def _ensure_default_cms_pages_seeded(self) -> None:
        """Seed default manageable public pages if cms_pages is empty."""
        existing = await self._repo.list_cms_pages()
        if existing:
            return

        now = datetime.now(UTC)
        for seed in DEFAULT_CMS_PAGES_SEED:
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
            page.sections = []
            page.versions = []
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
                sec.fields = []
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
                    sec.fields.append(field)
                page.sections.append(sec)
            await self._repo.create_cms_page(page)

    async def get_public_cms_page(self, slug: str) -> PublicCmsPageResponse:
        """Get live published content for a public CMS page."""
        await self._ensure_default_cms_pages_seeded()
        page = await self._repo.get_cms_page_by_slug(slug)
        if page is None:
            raise NotFoundError(f"CMS page '{slug}' not found.")

        sections_dict: dict[str, dict[str, Any]] = {}
        for sec in page.sections:
            if not sec.is_active:
                continue
            sec_fields: dict[str, Any] = {}
            for f in sec.fields:
                sec_fields[f.field_key] = f.published_value
            sections_dict[sec.section_key] = sec_fields

        return PublicCmsPageResponse(
            slug=page.slug,
            name=page.name,
            seo_title=page.seo_title,
            seo_description=page.seo_description,
            seo_keywords=page.seo_keywords,
            published_at=page.published_at,
            sections=sections_dict,
        )

    async def list_cms_pages(self) -> list[CmsPageResponse]:
        """List all manageable CMS pages for admin."""
        await self._ensure_default_cms_pages_seeded()
        pages = await self._repo.list_cms_pages()
        return [CmsPageResponse.model_validate(p) for p in pages]

    async def get_admin_cms_page(self, slug: str) -> CmsPageResponse:
        """Get detailed CMS page editor content for admin."""
        await self._ensure_default_cms_pages_seeded()
        page = await self._repo.get_cms_page_by_slug(slug)
        if page is None:
            raise NotFoundError(f"CMS page '{slug}' not found.")
        return CmsPageResponse.model_validate(page)

    async def update_admin_cms_page(
        self,
        slug: str,
        payload: CmsPageUpdate,
        user_id: uuid.UUID | None = None,
        ctx: RequestContext | None = None,
    ) -> CmsPageResponse:
        """Save draft changes for a CMS page and its section fields."""
        await self._ensure_default_cms_pages_seeded()
        page = await self._repo.get_cms_page_by_slug(slug)
        if page is None:
            raise NotFoundError(f"CMS page '{slug}' not found.")

        if payload.name is not None:
            page.name = payload.name
        if payload.description is not None:
            page.description = payload.description
        if payload.seo_title is not None:
            page.seo_title = payload.seo_title
        if payload.seo_description is not None:
            page.seo_description = payload.seo_description
        if payload.seo_keywords is not None:
            page.seo_keywords = payload.seo_keywords

        sec_map = {sec.section_key: sec for sec in page.sections}
        for sec_update in payload.sections:
            sec = sec_map.get(sec_update.section_key)
            if sec is None:
                sec = CmsSection(
                    page_id=page.id,
                    section_key=sec_update.section_key,
                    section_name=sec_update.section_name or sec_update.section_key.title(),
                    display_order=sec_update.display_order or 0,
                    is_active=sec_update.is_active if sec_update.is_active is not None else True,
                )
                page.sections.append(sec)
                sec_map[sec_update.section_key] = sec
            else:
                if sec_update.section_name is not None:
                    sec.section_name = sec_update.section_name
                if sec_update.display_order is not None:
                    sec.display_order = sec_update.display_order
                if sec_update.is_active is not None:
                    sec.is_active = sec_update.is_active

            field_map = {f.field_key: f for f in sec.fields}
            for f_update in sec_update.fields:
                f = field_map.get(f_update.field_key)
                if f is None:
                    f = CmsContentField(
                        section_id=sec.id,
                        field_key=f_update.field_key,
                        field_type=f_update.field_type or "text",
                        published_value=None,
                        draft_value=f_update.value,
                    )
                    sec.fields.append(f)
                else:
                    f.draft_value = f_update.value
                    if f_update.field_type:
                        f.field_type = f_update.field_type

        page.status = ContentStatus.DRAFT
        await self._repo.save_cms_page()

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.CMS_PAGE_DRAFT_SAVED,
                user_id=user_id,
                ip_address=ctx.ip_address if ctx else None,
                user_agent=ctx.user_agent if ctx else None,
                metadata={"action": "cms_draft_saved", "slug": slug},
            )

        return CmsPageResponse.model_validate(page)

    async def publish_admin_cms_page(
        self,
        slug: str,
        user_id: uuid.UUID | None = None,
        ctx: RequestContext | None = None,
    ) -> CmsPageResponse:
        """Publish draft content to public live state and record a version snapshot."""
        await self._ensure_default_cms_pages_seeded()
        page = await self._repo.get_cms_page_by_slug(slug)
        if page is None:
            raise NotFoundError(f"CMS page '{slug}' not found.")

        for sec in page.sections:
            for f in sec.fields:
                f.published_value = f.draft_value

        page.status = ContentStatus.PUBLISHED
        page.published_at = datetime.now(UTC)

        version_num = len(page.versions) + 1
        snapshot_data = {
            "slug": page.slug,
            "name": page.name,
            "seo_title": page.seo_title,
            "seo_description": page.seo_description,
            "seo_keywords": page.seo_keywords,
            "published_at": page.published_at.isoformat(),
            "sections": {
                sec.section_key: {
                    f.field_key: f.published_value for f in sec.fields
                }
                for sec in page.sections if sec.is_active
            },
        }

        version = CmsPageVersion(
            page_id=page.id,
            version_number=version_num,
            snapshot=snapshot_data,
            published_by=user_id,
        )
        await self._repo.create_cms_page_version(version)
        await self._repo.save_cms_page()

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.CMS_PAGE_PUBLISHED,
                user_id=user_id,
                ip_address=ctx.ip_address if ctx else None,
                user_agent=ctx.user_agent if ctx else None,
                metadata={"action": "cms_page_published", "slug": slug, "version": version_num},
            )

        return CmsPageResponse.model_validate(page)

    async def discard_admin_cms_page(
        self,
        slug: str,
        user_id: uuid.UUID | None = None,
        ctx: RequestContext | None = None,
    ) -> CmsPageResponse:
        """Discard draft changes and revert draft values back to published values."""
        await self._ensure_default_cms_pages_seeded()
        page = await self._repo.get_cms_page_by_slug(slug)
        if page is None:
            raise NotFoundError(f"CMS page '{slug}' not found.")

        for sec in page.sections:
            for f in sec.fields:
                f.draft_value = f.published_value

        page.status = ContentStatus.PUBLISHED
        await self._repo.save_cms_page()

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.CMS_PAGE_DRAFT_DISCARDED,
                user_id=user_id,
                ip_address=ctx.ip_address if ctx else None,
                user_agent=ctx.user_agent if ctx else None,
                metadata={"action": "cms_draft_discarded", "slug": slug},
            )

        return CmsPageResponse.model_validate(page)


DEFAULT_CMS_PAGES_SEED: list[dict[str, Any]] = [
    {
        "slug": "home",
        "name": "Home Page",
        "description": "Main landing page hero, mission, and emergency callouts",
        "seo_title": "PawGuard - Animal Rescue & Welfare Platform",
        "seo_description": "Connecting rescued animals with loving families across the community.",
        "seo_keywords": "dog rescue, adoption, animal welfare, shelter",
        "sections": [
            {
                "key": "hero",
                "name": "Hero Banner",
                "display_order": 1,
                "fields": [
                    {"key": "hero_badge", "type": "text", "value": "Every Paw Deserves a Home"},
                    {"key": "title", "type": "text", "value": "Find Your New Best Friend..."},
                    {"key": "subtitle", "type": "textarea", "value": "PawGuard connects rescued animals with loving families, helping every pet find a safe and caring forever home."},
                    {"key": "primary_cta_text", "type": "text", "value": "Adopt a Pet"},
                    {"key": "primary_cta_url", "type": "url", "value": "/adopt"},
                    {"key": "secondary_cta_text", "type": "text", "value": "Report Lost Pet"},
                    {"key": "secondary_cta_url", "type": "url", "value": "/lost-found"},
                    {"key": "hero_image_url", "type": "image", "value": "https://images.unsplash.com/photo-1543466835-00a7907e9de1"},
                ],
            },
            {
                "key": "mission",
                "name": "Mission Section",
                "display_order": 2,
                "fields": [
                    {"key": "heading", "type": "text", "value": "Our Core Mission"},
                    {"key": "body", "type": "textarea", "value": "Dedicated to rescuing street dogs, providing medical care, shelter, and matching them with caring forever homes."},
                ],
            },
            {
                "key": "cta",
                "name": "Emergency Rescue Banner",
                "display_order": 3,
                "fields": [
                    {"key": "heading", "type": "text", "value": "Emergency Rescue Needed?"},
                    {"key": "subheading", "type": "text", "value": "Our dispatch team operates 24/7 for stray rescue."},
                    {"key": "button_text", "type": "text", "value": "Report Incident"},
                    {"key": "button_url", "type": "url", "value": "/rescue"},
                ],
            },
        ],
    },
    {
        "slug": "about",
        "name": "About & Mission",
        "description": "Organization background, core values, and mission",
        "seo_title": "About PawGuard - Rescue & Welfare Mission",
        "seo_description": "Empowering communities to protect, rescue, and care for strays.",
        "seo_keywords": "about us, mission, animal welfare organization",
        "sections": [
            {
                "key": "hero",
                "name": "Hero Section",
                "display_order": 1,
                "fields": [
                    {"key": "title", "type": "text", "value": "About PawGuard"},
                    {"key": "subtitle", "type": "textarea", "value": "Empowering communities to protect, rescue, and care for strays."},
                ],
            },
            {
                "key": "vision",
                "name": "Our Vision",
                "display_order": 2,
                "fields": [
                    {"key": "heading", "type": "text", "value": "Our Vision"},
                    {"key": "body", "type": "textarea", "value": "A world where no animal suffers from neglect, injury, or homelessness."},
                ],
            },
        ],
    },
    {
        "slug": "adopt",
        "name": "Adoption Directory",
        "description": "Adoptable dog directory headers and guidelines",
        "seo_title": "Adoptable Dogs - PawGuard",
        "seo_description": "Browse rescued dogs ready for loving homes.",
        "seo_keywords": "adopt dog, adoptable pets, dog adoption process",
        "sections": [
            {
                "key": "hero",
                "name": "Hero Section",
                "display_order": 1,
                "fields": [
                    {"key": "title", "type": "text", "value": "Adoptable Dogs"},
                    {"key": "subtitle", "type": "textarea", "value": "Browse rescued dogs ready for loving homes."},
                    {"key": "notice", "type": "text", "value": "All dogs are vaccinated, dewormed, and microchipped."},
                ],
            },
            {
                "key": "process",
                "name": "Adoption Process",
                "display_order": 2,
                "fields": [
                    {"key": "heading", "type": "text", "value": "Adoption Workflow"},
                    {"key": "body", "type": "textarea", "value": "Submit an application -> Meet & Greet -> Home Check -> Welcome Home!"},
                ],
            },
        ],
    },
    {
        "slug": "rescue",
        "name": "Emergency Rescue Portal",
        "description": "Rescue hotline info and incident report guidance",
        "seo_title": "Emergency Rescue - PawGuard",
        "seo_description": "Report injured or distressed strays for immediate dispatch.",
        "seo_keywords": "dog rescue helpline, emergency stray rescue",
        "sections": [
            {
                "key": "hero",
                "name": "Hero Section",
                "display_order": 1,
                "fields": [
                    {"key": "title", "type": "text", "value": "Emergency Rescue Operations"},
                    {"key": "subtitle", "type": "textarea", "value": "Report injured or distressed strays for immediate dispatch."},
                    {"key": "hotline", "type": "text", "value": "+1 (800) 555-PAW1"},
                ],
            },
        ],
    },
    {
        "slug": "lost-found",
        "name": "Lost & Found Portal",
        "description": "Lost and found pet reporting guidance",
        "seo_title": "Lost & Found Pets - PawGuard",
        "seo_description": "Reuniting lost dogs with their owners across the community.",
        "seo_keywords": "lost dog, found pet, pet matching",
        "sections": [
            {
                "key": "hero",
                "name": "Hero Section",
                "display_order": 1,
                "fields": [
                    {"key": "title", "type": "text", "value": "Lost & Found Pets"},
                    {"key": "subtitle", "type": "textarea", "value": "Reuniting lost dogs with their owners across the community."},
                ],
            },
        ],
    },
    {
        "slug": "community",
        "name": "Community & Education",
        "description": "Community guidelines and awareness posts",
        "seo_title": "Community & Awareness - PawGuard",
        "seo_description": "Learn animal welfare practices, volunteer, or foster.",
        "seo_keywords": "community welfare, volunteer, foster",
        "sections": [
            {
                "key": "hero",
                "name": "Hero Section",
                "display_order": 1,
                "fields": [
                    {"key": "title", "type": "text", "value": "Community & Awareness"},
                    {"key": "subtitle", "type": "textarea", "value": "Learn animal welfare practices, volunteer, or foster."},
                ],
            },
        ],
    },
    {
        "slug": "donate",
        "name": "Donation Gateway",
        "description": "Donation appeal banners and tax exemption info",
        "seo_title": "Donate & Support - PawGuard",
        "seo_description": "Your contributions fund medical surgeries, food, shelter, and rescue runs.",
        "seo_keywords": "donate animal shelter, 80G tax exemption, dog rescue donation",
        "sections": [
            {
                "key": "hero",
                "name": "Hero Section",
                "display_order": 1,
                "fields": [
                    {"key": "title", "type": "text", "value": "Support Our Mission"},
                    {"key": "subtitle", "type": "textarea", "value": "Your contributions fund medical surgeries, food, shelter, and rescue runs."},
                    {"key": "tax_info", "type": "text", "value": "80G Tax Exemption Eligible."},
                ],
            },
        ],
    },
    {
        "slug": "contact",
        "name": "Contact & Shelters",
        "description": "Contact info, operating hours, and location headers",
        "seo_title": "Contact Us - PawGuard",
        "seo_description": "Find shelter addresses, emergency hotlines, and operating hours.",
        "seo_keywords": "contact pawguard, shelter location, emergency phone",
        "sections": [
            {
                "key": "hero",
                "name": "Hero Section",
                "display_order": 1,
                "fields": [
                    {"key": "title", "type": "text", "value": "Get in Touch"},
                    {"key": "subtitle", "type": "textarea", "value": "Find shelter addresses, emergency hotlines, and operating hours."},
                ],
            },
        ],
    },
    {
        "slug": "faq",
        "name": "FAQ & Help Center",
        "description": "Frequently asked questions header and metadata",
        "seo_title": "Frequently Asked Questions - PawGuard",
        "seo_description": "Find answers to common questions about rescue, adoption, and volunteering.",
        "seo_keywords": "faq, pawguard help, adoption questions",
        "sections": [
            {
                "key": "hero",
                "name": "Hero Section",
                "display_order": 1,
                "fields": [
                    {"key": "title", "type": "text", "value": "Frequently Asked Questions"},
                    {"key": "subtitle", "type": "textarea", "value": "Find answers to common questions about rescue, adoption, and volunteering."},
                ],
            },
        ],
    },
]
