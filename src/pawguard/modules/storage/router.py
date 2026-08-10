"""API router for the Storage module. Routers only validate and call services (RULE-004)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import BulkDeleteRequest, BulkDeleteResponse
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import (
    CurrentUser,
    get_current_user,
    get_optional_current_user,
)
from pawguard.modules.storage.models import FileFolder
from pawguard.modules.storage.repository import StorageRepository
from pawguard.modules.storage.schemas import (
    DownloadUrlResponse,
    StoredFileCreate,
    StoredFileResponse,
    UploadUrlResponse,
)
from pawguard.modules.storage.service import StorageService
from pawguard.services.storage_service import StorageService as S3StorageService

router = APIRouter(prefix="/storage", tags=["storage"])


def get_storage_service(
    db: AsyncSession = Depends(get_db),
) -> StorageService:
    return StorageService(StorageRepository(db), S3StorageService())


@router.post(
    "/upload-url",
    response_model=ApiResponse[UploadUrlResponse],
    status_code=status.HTTP_201_CREATED,
)
async def request_upload_url(
    payload: StoredFileCreate,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: StorageService = Depends(get_storage_service),
) -> ApiResponse[UploadUrlResponse]:
    result = await service.request_upload_url(
        payload, user_id=current_user.id if current_user else None
    )
    return ApiResponse(data=result, message="Upload URL generated successfully.")


@router.put(
    "/{file_id}/confirm",
    response_model=ApiResponse[StoredFileResponse],
)
async def confirm_upload(
    file_id: uuid.UUID,
    batch_file_ids: str | None = Query(
        None,
        description="Comma-separated batch file IDs for combined size check",
    ),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: StorageService = Depends(get_storage_service),
) -> ApiResponse[StoredFileResponse]:
    ids = (
        [uuid.UUID(fid.strip()) for fid in batch_file_ids.split(",") if fid.strip()]
        if batch_file_ids
        else None
    )
    stored = await service.confirm_upload(file_id, batch_file_ids=ids)
    return ApiResponse(
        data=StoredFileResponse.model_validate(stored),
        message="Upload confirmed successfully.",
    )


@router.get(
    "/{file_id}/download-url",
    response_model=ApiResponse[DownloadUrlResponse],
)
async def get_download_url(
    file_id: uuid.UUID,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    service: StorageService = Depends(get_storage_service),
) -> ApiResponse[DownloadUrlResponse]:
    result = await service.get_download_url(file_id)
    return ApiResponse(data=result)


@router.get(
    "/{file_id}",
    response_model=ApiResponse[StoredFileResponse],
)
async def get_file(
    file_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
) -> ApiResponse[StoredFileResponse]:
    stored = await service.get_file(file_id)
    return ApiResponse(data=StoredFileResponse.model_validate(stored))


@router.get(
    "",
    response_model=PaginatedResponse[StoredFileResponse],
)
async def list_files(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by filename, folder, or MIME type"),
    folder: FileFolder | None = Query(None, description="Filter by folder"),
    mime_type: str | None = Query(None, description="Filter by MIME type"),
    is_uploaded: bool | None = Query(None, description="Filter by upload status"),
    current_user: CurrentUser = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
) -> PaginatedResponse[StoredFileResponse]:
    is_admin = await service.is_admin_user(current_user)
    return await service.list_files_paginated(
        page=page,
        sort=sort,
        search_term=search,
        folder=folder.value if folder else None,
        mime_type=mime_type,
        is_uploaded=is_uploaded,
        user_id=None if is_admin else current_user.id,
    )


@router.delete(
    "/{file_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_file(
    file_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
) -> ApiResponse[None]:
    await service.delete_file(
        file_id,
        current_user=current_user,
    )
    return ApiResponse(message="File deleted successfully.")


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
)
async def bulk_delete_files(
    payload: BulkDeleteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
) -> ApiResponse[BulkDeleteResponse]:
    deleted = await service.bulk_delete_files(
        payload.ids,
        current_user=current_user,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} file(s) deleted.",
            deleted_count=deleted,
        ),
    )


@router.get(
    "/entity/{entity_type}/{entity_id}",
    response_model=PaginatedResponse[StoredFileResponse],
)
async def list_files_by_entity(
    entity_type: str,
    entity_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    folder: FileFolder | None = Query(None, description="Filter by folder"),
    current_user: CurrentUser = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
) -> PaginatedResponse[StoredFileResponse]:
    return await service.list_by_entity(
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        sort=sort,
        folder=folder.value if folder else None,
    )

