"""Pydantic schemas for the Storage module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from pawguard.modules.storage.models import FileFolder


class StoredFileCreate(BaseModel):
    original_filename: str = Field(..., min_length=1, max_length=512)
    mime_type: str = Field(..., min_length=1, max_length=128)
    file_size: int = Field(..., ge=0)
    folder: FileFolder
    entity_type: str | None = Field(None, max_length=64)
    entity_id: uuid.UUID | None = None


class StoredFileUpdate(BaseModel):
    is_uploaded: bool = True


class StoredFileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    object_key: str
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

    class Config:
        from_attributes = True


class UploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str
    file_id: uuid.UUID


class DownloadUrlResponse(BaseModel):
    download_url: str
    object_key: str
    file_id: uuid.UUID
