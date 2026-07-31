"""PortalService: owns CMS content and public portal business behaviour (RULE-003)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginationMeta
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.donation.models import Donation, DonorProfile
from pawguard.modules.foster.models import FosterProfile
from pawguard.modules.lost_found.models import FoundReport, LostReport
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
    PublicHeroStats,
    SuccessStoryCreate,
    SuccessStoryUpdate,
    UserDashboardSummary,
    VeterinaryPartnerCreate,
    VeterinaryPartnerUpdate,
)
from pawguard.modules.rescue.models import RescueRequest, RescueStatus
from pawguard.modules.settings.models import SystemSetting
from pawguard.modules.volunteer.models import VolunteerProfile
from pawguard.services.audit_service import AuditService


class PortalService:
    def __init__(
        self,
        repository: PortalRepository,
        session: AsyncSession,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._session = session
        self._audit = audit_service

    def _apply_publish(
        self,
        status: ContentStatus,
        entity: SuccessStory | BlogPost,
    ) -> None:
        if status == ContentStatus.PUBLISHED and entity.published_at is None:
            entity.published_at = datetime.now(UTC)
        if status == ContentStatus.DRAFT:
            entity.published_at = None

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
        return await self._repo.create_vet(
            VeterinaryPartner(**payload.model_dump())
        )

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
                )
            )
        ).scalar_one()
        return PublicHeroStats(
            total_rescued=total_rescued,
            active_care_count=active_care,
            successful_adoptions=adoptions,
            urgent_rescue_count=urgent,
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
