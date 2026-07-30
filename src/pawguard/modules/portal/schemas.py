"""Pydantic schemas for the public portal CMS module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.portal.models import ContentStatus


class SuccessStoryCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    summary: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    hero_image_url: str | None = Field(None, max_length=512)
    dog_id: uuid.UUID | None = None
    status: ContentStatus = ContentStatus.DRAFT


class SuccessStoryUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    summary: str | None = None
    body: str | None = None
    hero_image_url: str | None = Field(None, max_length=512)
    dog_id: uuid.UUID | None = None
    status: ContentStatus | None = None


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
    title: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    excerpt: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    cover_image_url: str | None = Field(None, max_length=512)
    category: str = Field("awareness", max_length=128)
    status: ContentStatus = ContentStatus.DRAFT


class BlogPostUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    excerpt: str | None = None
    body: str | None = None
    cover_image_url: str | None = Field(None, max_length=512)
    category: str | None = Field(None, max_length=128)
    status: ContentStatus | None = None


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
    name: str = Field(..., min_length=1, max_length=255)
    address: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=5, max_length=32)
    email: str | None = Field(None, max_length=255)
    latitude: float | None = None
    longitude: float | None = None
    is_emergency: bool = False
    services: str | None = None
    is_active: bool = True


class VeterinaryPartnerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = Field(None, min_length=5, max_length=32)
    email: str | None = Field(None, max_length=255)
    latitude: float | None = None
    longitude: float | None = None
    is_emergency: bool | None = None
    services: str | None = None
    is_active: bool | None = None


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
    name: str = Field(..., min_length=1, max_length=255)
    address: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=5, max_length=32)
    email: str | None = Field(None, max_length=255)
    operating_hours: str | None = Field(None, max_length=255)
    is_emergency_hotline: bool = False
    sort_order: int = 0


class ContactLocationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = Field(None, min_length=5, max_length=32)
    email: str | None = Field(None, max_length=255)
    operating_hours: str | None = Field(None, max_length=255)
    is_emergency_hotline: bool | None = None
    sort_order: int | None = None


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
    question: str = Field(..., min_length=1, max_length=512)
    answer: str = Field(..., min_length=1)
    category: str = Field("general", max_length=128)
    sort_order: int = 0
    is_published: bool = True


class FAQEntryUpdate(BaseModel):
    question: str | None = Field(None, min_length=1, max_length=512)
    answer: str | None = None
    category: str | None = Field(None, max_length=128)
    sort_order: int | None = None
    is_published: bool | None = None


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
    value: str = Field(..., min_length=1)
    description: str | None = Field(None, max_length=255)


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
