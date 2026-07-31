"""Pydantic schemas for the public portal CMS module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.portal.models import ContentStatus


class SuccessStoryCreate(BaseModel):
    title: str = Field(
        ..., min_length=1, max_length=255, examples=["From Stray to Star: Barnaby's Journey"]
    )
    summary: str = Field(
        ..., min_length=1,
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


class SuccessStoryUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255, examples=["Updated title"])
    summary: str | None = Field(None, examples=["Updated summary."])
    body: str | None = Field(None, examples=["Updated story body."])
    hero_image_url: str | None = Field(None, max_length=512, examples=["https://example.com/updated.jpg"])
    dog_id: uuid.UUID | None = None
    status: ContentStatus | None = Field(None, examples=["published"])


class SuccessStoryResponse(BaseModel):
    id: uuid.UUID
    title: str
    summary: str
    body: str
    hero_image_url: str | None
    dog_id: uuid.UUID | None
    status: ContentStatus
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BlogPostCreate(BaseModel):
    title: str = Field(
        ..., min_length=1, max_length=255,
        examples=["5 Signs Your New Rescue Dog Needs a Vet Visit"],
    )
    slug: str = Field(
        ..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$",
        examples=["5-signs-your-rescue-dog-needs-a-vet-visit"],
    )
    excerpt: str = Field(
        ..., min_length=1, examples=["Know the early warning signs to watch for."]
    )
    body: str = Field(
        ..., min_length=1,
        examples=["When you bring home a rescue dog, the first few weeks..."],
    )
    cover_image_url: str | None = Field(None, max_length=512, examples=["https://example.com/blog/cover.jpg"])
    category: str = Field("awareness", max_length=128, examples=["pet_care"])
    status: ContentStatus = ContentStatus.DRAFT


class BlogPostUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255, examples=["Updated title"])
    slug: str | None = Field(
        None, min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$", examples=["updated-slug"]
    )
    excerpt: str | None = Field(None, examples=["Updated excerpt."])
    body: str | None = Field(None, examples=["Updated body content."])
    cover_image_url: str | None = Field(None, max_length=512, examples=["https://example.com/updated.jpg"])
    category: str | None = Field(None, max_length=128, examples=["pet_care"])
    status: ContentStatus | None = Field(None, examples=["published"])


class BlogPostResponse(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    excerpt: str
    body: str
    cover_image_url: str | None
    category: str
    status: ContentStatus
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

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


class UserDashboardSummary(BaseModel):
    rescue_cases: list[dict[str, Any]]
    adoption_applications: list[dict[str, Any]]
    volunteer_profile: dict[str, Any] | None
    foster_profile: dict[str, Any] | None
    donations: list[dict[str, Any]]
    lost_found_reports: list[dict[str, Any]]
