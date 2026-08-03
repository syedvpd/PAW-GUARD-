"""Pydantic schemas for the Storage module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pawguard.core.upload import ALLOWED_MIME_TYPES, MAX_FILE_SIZE_BYTES
from pawguard.modules.storage.models import FileFolder


class StoredFileCreate(BaseModel):
    original_filename: str = Field(
        ..., min_length=1, max_length=512, examples=["barnaby_intake.jpg"]
    )
    mime_type: str = Field(..., min_length=1, max_length=128, examples=["image/jpeg"])
    file_size: int = Field(..., gt=0, le=MAX_FILE_SIZE_BYTES, examples=[204800])
    folder: FileFolder = Field(..., examples=["dogs"])
    entity_type: str | None = Field(None, max_length=64, examples=["dog_profile"])
    entity_id: uuid.UUID | None = None

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        if value not in ALLOWED_MIME_TYPES:
            raise ValueError(
                f"Unsupported file type '{value}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}."
            )
        return value


class StoredFileUpdate(BaseModel):
    is_uploaded: bool = True


class StoredFileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    object_key: str
    thumbnail_object_key: str | None
    original_filename: str
    mime_type: str
    file_size: int
    folder: str
    is_uploaded: bool
    uploaded_at: datetime | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str
    file_id: uuid.UUID


class DownloadUrlResponse(BaseModel):
    download_url: str
    object_key: str
    file_id: uuid.UUID
