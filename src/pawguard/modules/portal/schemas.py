"""Pydantic schemas for the public portal CMS module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pawguard.modules.portal.models import (
    AlertSeverity,
    ContentStatus,
    LegalDocumentType,
)


class SuccessStoryCreate(BaseModel):
    title: str = Field(
        ..., min_length=1, max_length=255, examples=["From Stray to Star: Barnaby's Journey"]
    )
    summary: str = Field(
        ...,
        min_length=1,
        examples=["Rescued injured and malnourished, now thriving with his new family."],
    )
    body: str = Field(
        ..., min_length=1, examples=["Barnaby was found on Sector 4 with a fractured leg..."]
    )
    hero_image_url: str | None = Field(
        None, max_length=512, examples=["https://example.com/barnaby-hero.jpg"]
    )
    dog_id: uuid.UUID | None = None
    status: ContentStatus = ContentStatus.DRAFT
    slug: str | None = Field(None, pattern=r"^[a-z0-9-]+$", examples=["from-stray-to-star-barnaby"])
    is_featured: bool = False
    sort_order: int = 0


class SuccessStoryUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255, examples=["Updated title"])
    summary: str | None = Field(None, examples=["Updated summary."])
    body: str | None = Field(None, examples=["Updated story body."])
    hero_image_url: str | None = Field(
        None, max_length=512, examples=["https://example.com/updated.jpg"]
    )
    dog_id: uuid.UUID | None = None
    status: ContentStatus | None = Field(None, examples=["published"])
    slug: str | None = Field(None, pattern=r"^[a-z0-9-]+$", examples=["updated-slug"])
    is_featured: bool | None = None
    sort_order: int | None = None


class SuccessStoryResponse(BaseModel):
    id: uuid.UUID
    title: str
    summary: str
    body: str
    hero_image_url: str | None = None
    cover_image_url: str | None = None
    image_url: str | None = None
    photo_url: str | None = None
    image: str | None = None
    media_url: str | None = None
    imageUrl: str | None = None
    photoUrl: str | None = None
    coverImage: str | None = None
    story_image: str | None = None
    banner_url: str | None = None
    thumbnail_url: str | None = None
    thumbnail: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    photo_gallery_urls: list[str] = Field(default_factory=list)
    photos: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    dog_id: uuid.UUID | None
    status: ContentStatus
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    slug: str | None = None
    is_featured: bool = False
    sort_order: int = 0

    @model_validator(mode="after")
    def _sync_image_fields(self) -> "SuccessStoryResponse":
        img = (
            self.hero_image_url
            or self.cover_image_url
            or self.image_url
            or self.photo_url
            or self.image
            or self.media_url
            or self.imageUrl
            or self.photoUrl
            or self.coverImage
            or self.story_image
            or self.banner_url
            or self.thumbnail_url
            or self.thumbnail
            or (self.image_urls[0] if self.image_urls else None)
            or (self.photo_gallery_urls[0] if self.photo_gallery_urls else None)
            or (self.photos[0] if self.photos else None)
            or (self.images[0] if self.images else None)
        )
        if img:
            if not img.startswith("http"):
                try:
                    from pawguard.services.storage_service import get_storage_service
                    img = get_storage_service().generate_presigned_download_url(object_key=img)
                except Exception:
                    pass
            self.hero_image_url = img
            self.cover_image_url = img
            self.image_url = img
            self.photo_url = img
            self.image = img
            self.media_url = img
            self.imageUrl = img
            self.photoUrl = img
            self.coverImage = img
            self.story_image = img
            self.banner_url = img
            self.thumbnail_url = img
            self.thumbnail = img
            self.image_urls = [img]
            self.photo_gallery_urls = [img]
            self.photos = [img]
            self.images = [img]
        return self

    model_config = ConfigDict(from_attributes=True)


class BlogPostCreate(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["5 Signs Your New Rescue Dog Needs a Vet Visit"],
    )
    slug: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9-]+$",
        examples=["5-signs-your-rescue-dog-needs-a-vet-visit"],
    )
    excerpt: str = Field(..., min_length=1, examples=["Know the early warning signs to watch for."])
    body: str = Field(
        ...,
        min_length=1,
        examples=["When you bring home a rescue dog, the first few weeks..."],
    )
    cover_image_url: str | None = Field(
        None, max_length=512, examples=["https://example.com/blog/cover.jpg"]
    )
    category: str = Field("awareness", max_length=128, examples=["pet_care"])
    status: ContentStatus = ContentStatus.DRAFT
    tags: str | None = Field(None, max_length=255, examples=["pet_care, vet_visit"])
    author: str | None = Field(None, max_length=255, examples=["Dr. Jane Smith"])


class BlogPostUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255, examples=["Updated title"])
    slug: str | None = Field(
        None, min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$", examples=["updated-slug"]
    )
    excerpt: str | None = Field(None, examples=["Updated excerpt."])
    body: str | None = Field(None, examples=["Updated body content."])
    cover_image_url: str | None = Field(
        None, max_length=512, examples=["https://example.com/updated.jpg"]
    )
    category: str | None = Field(None, max_length=128, examples=["pet_care"])
    status: ContentStatus | None = Field(None, examples=["published"])
    tags: str | None = Field(None, max_length=255, examples=["pet_care, vet_visit"])
    author: str | None = Field(None, max_length=255, examples=["Dr. Jane Smith"])


class BlogPostResponse(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    excerpt: str
    body: str
    cover_image_url: str | None = None
    image_url: str | None = None
    photo_url: str | None = None
    image: str | None = None
    hero_image_url: str | None = None
    media_url: str | None = None
    imageUrl: str | None = None
    photoUrl: str | None = None
    coverImage: str | None = None
    story_image: str | None = None
    banner_url: str | None = None
    thumbnail_url: str | None = None
    thumbnail: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    photo_gallery_urls: list[str] = Field(default_factory=list)
    photos: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    category: str
    status: ContentStatus
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tags: str | None = None
    author: str | None = None

    @model_validator(mode="after")
    def _sync_image_fields(self) -> "BlogPostResponse":
        img = (
            self.cover_image_url
            or self.image_url
            or self.photo_url
            or self.image
            or self.hero_image_url
            or self.media_url
            or self.imageUrl
            or self.photoUrl
            or self.coverImage
            or self.story_image
            or self.banner_url
            or self.thumbnail_url
            or self.thumbnail
            or (self.image_urls[0] if self.image_urls else None)
            or (self.photo_gallery_urls[0] if self.photo_gallery_urls else None)
            or (self.photos[0] if self.photos else None)
            or (self.images[0] if self.images else None)
        )
        if img:
            if not img.startswith("http"):
                try:
                    from pawguard.services.storage_service import get_storage_service
                    img = get_storage_service().generate_presigned_download_url(object_key=img)
                except Exception:
                    pass
            self.cover_image_url = img
            self.image_url = img
            self.photo_url = img
            self.image = img
            self.hero_image_url = img
            self.media_url = img
            self.imageUrl = img
            self.photoUrl = img
            self.coverImage = img
            self.story_image = img
            self.banner_url = img
            self.thumbnail_url = img
            self.thumbnail = img
            self.image_urls = [img]
            self.photo_gallery_urls = [img]
            self.photos = [img]
            self.images = [img]
        return self

    model_config = ConfigDict(from_attributes=True)


class VeterinaryPartnerCreate(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=255, examples=["Central Emergency Vet Hospital"]
    )
    address: str = Field(..., min_length=1, examples=["78 Health Avenue, Sector 2"])
    phone: str = Field(..., min_length=5, max_length=32, examples=["+1-555-0144"])
    email: str | None = Field(None, max_length=255, examples=["contact@centralvet.example.com"])
    latitude: float | None = Field(None, examples=[17.4400])
    longitude: float | None = Field(None, examples=[78.3900])
    is_emergency: bool = False
    services: str | None = Field(None, examples=["24/7 emergency care, surgery, radiology"])
    is_active: bool = True


class VeterinaryPartnerUpdate(BaseModel):
    name: str | None = Field(
        None, min_length=1, max_length=255, examples=["Central Emergency Vet Hospital"]
    )
    address: str | None = Field(None, examples=["78 Health Avenue, Sector 2"])
    phone: str | None = Field(None, min_length=5, max_length=32, examples=["+1-555-0144"])
    email: str | None = Field(None, max_length=255, examples=["contact@centralvet.example.com"])
    latitude: float | None = Field(None, examples=[17.4400])
    longitude: float | None = Field(None, examples=[78.3900])
    is_emergency: bool | None = Field(None, examples=[True])
    services: str | None = Field(None, examples=["24/7 emergency care, surgery, radiology"])
    is_active: bool | None = Field(None, examples=[True])


class VeterinaryPartnerResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    phone: str
    email: str | None
    latitude: float | None
    longitude: float | None
    is_emergency: bool
    services: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactLocationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Central Shelter Alpha"])
    address: str = Field(..., min_length=1, examples=["45 Rescue Road, Sector 4"])
    phone: str = Field(..., min_length=5, max_length=32, examples=["+1-555-0111"])
    email: str | None = Field(None, max_length=255, examples=["central@pawguard.example.com"])
    operating_hours: str | None = Field(None, max_length=255, examples=["Mon-Sat, 9am-6pm"])
    is_emergency_hotline: bool = False
    sort_order: int = Field(0, examples=[1])


class ContactLocationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255, examples=["Central Shelter Alpha"])
    address: str | None = Field(None, examples=["45 Rescue Road, Sector 4"])
    phone: str | None = Field(None, min_length=5, max_length=32, examples=["+1-555-0111"])
    email: str | None = Field(None, max_length=255, examples=["central@pawguard.example.com"])
    operating_hours: str | None = Field(None, max_length=255, examples=["Mon-Sat, 9am-6pm"])
    is_emergency_hotline: bool | None = Field(None, examples=[False])
    sort_order: int | None = Field(None, examples=[1])


class ContactLocationResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    phone: str
    email: str | None
    operating_hours: str | None
    is_emergency_hotline: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactMessageCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    subject: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=10000)


class NewsletterSubscribeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


class NewsletterSubscriptionResponse(BaseModel):
    subscribed: bool


class FAQEntryCreate(BaseModel):
    question: str = Field(
        ..., min_length=1, max_length=512, examples=["How long does the adoption process take?"]
    )
    answer: str = Field(
        ..., min_length=1, examples=["Typically 2-3 weeks from application to home visit."]
    )
    category: str = Field("general", max_length=128, examples=["adoption"])
    sort_order: int = Field(0, examples=[1])
    is_published: bool = True


class FAQEntryUpdate(BaseModel):
    question: str | None = Field(None, min_length=1, max_length=512, examples=["Updated question?"])
    answer: str | None = Field(None, examples=["Updated answer."])
    category: str | None = Field(None, max_length=128, examples=["adoption"])
    sort_order: int | None = Field(None, examples=[2])
    is_published: bool | None = Field(None, examples=[True])


class FAQEntryResponse(BaseModel):
    id: uuid.UUID
    question: str
    answer: str
    category: str
    sort_order: int
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SystemSettingUpsert(BaseModel):
    value: str = Field(..., min_length=1, examples=["25"])
    description: str | None = Field(
        None, max_length=255, examples=["Maximum dispatch radius in km."]
    )


class SystemSettingResponse(BaseModel):
    id: uuid.UUID
    key: str
    value: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicHeroStats(BaseModel):
    total_rescued: int
    active_care_count: int
    successful_adoptions: int
    urgent_rescue_count: int


class LegalDocumentCreate(BaseModel):
    slug: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9-]+$",
        examples=["terms-of-service"],
    )
    title: str = Field(..., min_length=1, max_length=255, examples=["Terms of Service"])
    document_type: LegalDocumentType = LegalDocumentType.OTHER
    body: str = Field(..., min_length=1, examples=["1. Acceptance of Terms..."])
    version: str = Field("1.0", max_length=32, examples=["1.0"])
    status: ContentStatus = ContentStatus.DRAFT


class LegalDocumentUpdate(BaseModel):
    slug: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9-]+$",
        examples=["terms-of-service"],
    )
    title: str | None = Field(None, min_length=1, max_length=255, examples=["Terms of Service"])
    document_type: LegalDocumentType | None = Field(None, examples=["terms"])
    body: str | None = Field(None, min_length=1, examples=["1. Acceptance of Terms..."])
    version: str | None = Field(None, max_length=32, examples=["2.0"])
    status: ContentStatus | None = Field(None, examples=["published"])


class LegalDocumentResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    document_type: LegalDocumentType
    body: str
    version: str
    status: ContentStatus
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UrgentAlertCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, examples=["Flooding in Sector 4"])
    message: str = Field(
        ..., min_length=1, examples=["Roads are flooded; rescue teams are on standby."]
    )
    severity: AlertSeverity = AlertSeverity.INFO
    is_active: bool = True
    starts_at: datetime | None = Field(None, examples=["2026-08-02T09:00:00Z"])
    ends_at: datetime | None = Field(None, examples=["2026-08-03T09:00:00Z"])
    sort_order: int = Field(0, examples=[1])


class UrgentAlertUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255, examples=["Flooding in Sector 4"])
    message: str | None = Field(None, min_length=1, examples=["Updated alert message."])
    severity: AlertSeverity | None = Field(None, examples=["critical"])
    is_active: bool | None = Field(None, examples=[True])
    starts_at: datetime | None = Field(None, examples=["2026-08-02T09:00:00Z"])
    ends_at: datetime | None = Field(None, examples=["2026-08-03T09:00:00Z"])
    sort_order: int | None = Field(None, examples=[1])


class UrgentAlertResponse(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    severity: AlertSeverity
    is_active: bool
    starts_at: datetime | None
    ends_at: datetime | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransparencyStats(BaseModel):
    total_funds_raised: float
    total_donations: int
    total_rescues_completed: int
    successful_adoptions: int
    active_volunteers: int
    active_foster_homes: int
    veterinary_partners: int
    dogs_in_care: int


class UserDashboardSummary(BaseModel):
    rescue_cases: list[dict[str, Any]]
    adoption_applications: list[dict[str, Any]]
    volunteer_profile: dict[str, Any] | None
    volunteer_status: str | None = Field(
        None,
        description="Current volunteer lifecycle state: NOT_APPLIED, PENDING, ACTIVE, REJECTED, INACTIVE",
    )
    volunteer_application: dict[str, Any] | None
    foster_profile: dict[str, Any] | None
    donations: list[dict[str, Any]]
    lost_found_reports: list[dict[str, Any]]


# ── Dynamic CMS Schemas ──────────────────────────────────────────────────────


class CmsFieldUpdate(BaseModel):
    field_key: str
    field_type: str = "text"
    value: str | None = None


class CmsSectionUpdate(BaseModel):
    section_key: str
    section_name: str | None = None
    display_order: int | None = None
    is_active: bool | None = None
    fields: list[CmsFieldUpdate] = Field(default_factory=list)


class CmsPageUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    seo_title: str | None = None
    seo_description: str | None = None
    seo_keywords: str | None = None
    sections: list[CmsSectionUpdate] = Field(default_factory=list)


class CmsFieldResponse(BaseModel):
    id: uuid.UUID
    field_key: str
    field_type: str
    published_value: str | None
    draft_value: str | None
    published_url: str | None = None
    draft_url: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _resolve_urls(self) -> "CmsFieldResponse":
        if self.field_type in ("image", "video", "media", "file"):
            import contextlib

            try:
                from pawguard.services.storage_service import get_storage_service

                s3 = get_storage_service()
            except Exception:
                s3 = None

            if s3:
                if self.published_value and not self.published_value.startswith("http"):
                    with contextlib.suppress(Exception):
                        self.published_url = s3.generate_presigned_download_url(
                            object_key=self.published_value
                        )
                else:
                    self.published_url = self.published_value

                if self.draft_value and not self.draft_value.startswith("http"):
                    with contextlib.suppress(Exception):
                        self.draft_url = s3.generate_presigned_download_url(
                            object_key=self.draft_value
                        )
                else:
                    self.draft_url = self.draft_value
            else:
                self.published_url = self.published_value
                self.draft_url = self.draft_value
        else:
            self.published_url = self.published_value
            self.draft_url = self.draft_value
        return self


class CmsSectionResponse(BaseModel):
    id: uuid.UUID
    section_key: str
    section_name: str
    display_order: int
    is_active: bool
    fields: list[CmsFieldResponse]

    model_config = ConfigDict(from_attributes=True)


class CmsPageResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    seo_title: str | None
    seo_description: str | None
    seo_keywords: str | None
    status: ContentStatus
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    sections: list[CmsSectionResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PublicCmsPageResponse(BaseModel):
    slug: str
    name: str
    seo_title: str | None
    seo_description: str | None
    seo_keywords: str | None
    published_at: datetime | None
    sections: dict[str, dict[str, Any]]
