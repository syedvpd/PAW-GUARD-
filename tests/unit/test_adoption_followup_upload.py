import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.adoption.router import generate_follow_up_upload_url
from pawguard.modules.adoption.schemas import AdoptionFollowUpUploadUrlRequest
from pawguard.modules.auth.dependencies import CurrentUser


@pytest.fixture
def mock_current_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.user = user
    user.roles = ["ADOPTION_COORDINATOR"]
    user.permissions = ["adoption:process", "adoption:read"]
    return CurrentUser(user=user, claims={}, db=MagicMock(), redis=MagicMock())


@pytest.mark.asyncio
async def test_generate_follow_up_upload_url_success(mock_current_user):
    app_id = uuid.uuid4()
    mock_app = MagicMock(spec=AdoptionApplication)
    mock_app.id = app_id
    mock_app.adopter_id = mock_current_user.id
    mock_app.status = AdoptionStatus.COMPLETED

    mock_service = MagicMock()
    mock_service.get_application = AsyncMock(return_value=mock_app)

    payload = AdoptionFollowUpUploadUrlRequest(
        filename="followup_welfare_photo.jpg",
        mime_type="image/jpeg",
        file_size=1024 * 1024,
    )

    with patch("pawguard.modules.adoption.router.StorageService") as MockStorageService:
        mock_storage = MagicMock()
        mock_storage.build_object_key.return_value = "documents/followup_12345.jpg"
        mock_storage.generate_presigned_upload_url.return_value = (
            "https://s3.amazonaws.com/upload-url"
        )
        MockStorageService.return_value = mock_storage

        res = await generate_follow_up_upload_url(
            app_id=app_id,
            payload=payload,
            current_user=mock_current_user,
            service=mock_service,
        )

    assert res.data is not None
    assert res.data.upload_url == "https://s3.amazonaws.com/upload-url"
    assert res.data.media_key == "documents/followup_12345.jpg"
