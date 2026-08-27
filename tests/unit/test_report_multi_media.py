"""Unit tests for multi-media support across Lost, Found, and Emergency Rescue reports."""

from unittest.mock import MagicMock, patch

import pytest

from pawguard.core.exceptions import ValidationFailedError
from pawguard.modules.lost_found.schemas import (
    FoundReportCreate,
    LostReportCreate,
)
from pawguard.modules.rescue.schemas import (
    RescuePhysicalCondition,
    RescueRequestCreate,
)
from pawguard.services.storage_service import StorageService


class TestReportMultiMediaValidation:
    """Test storage validation logic for photos and videos."""

    def test_zero_media_valid(self) -> None:
        svc = StorageService()
        # Should not raise
        svc.validate_report_media(photo_keys=[], video_key=None)

    def test_five_photos_valid(self) -> None:
        svc = StorageService()
        photos = [f"lost-found/photo_{i}.jpg" for i in range(5)]
        # Should not raise
        svc.validate_report_media(photo_keys=photos, video_key=None)

    def test_six_photos_raises_validation_error(self) -> None:
        svc = StorageService()
        photos = [f"lost-found/photo_{i}.jpg" for i in range(6)]
        with pytest.raises(ValidationFailedError, match="Maximum 5 photos allowed"):
            svc.validate_report_media(photo_keys=photos, video_key=None)

    def test_one_video_valid(self) -> None:
        svc = StorageService()
        # Should not raise
        svc.validate_report_media(photo_keys=[], video_key="lost-found/clip.mp4")

    def test_five_photos_and_one_video_valid(self) -> None:
        svc = StorageService()
        photos = [f"rescue/photo_{i}.jpg" for i in range(5)]
        # Should not raise
        svc.validate_report_media(photo_keys=photos, video_key="rescue/clip.mp4")

    def test_unsupported_image_mime_type_raises(self) -> None:
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentType": "image/gif", "ContentLength": 1000}
        with patch("pawguard.services.storage_service.boto3.client", return_value=mock_client):
            svc = StorageService()

            with pytest.raises(ValidationFailedError, match="Unsupported image type"):
                svc.validate_report_media(photo_keys=["lost-found/bad.gif"], video_key=None)

    def test_unsupported_video_mime_type_raises(self) -> None:
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentType": "video/avi", "ContentLength": 500000}
        with patch("pawguard.services.storage_service.boto3.client", return_value=mock_client):
            svc = StorageService()

            with pytest.raises(ValidationFailedError, match="Unsupported video type"):
                svc.validate_report_media(photo_keys=[], video_key="lost-found/bad.avi")

    def test_oversized_photo_raises(self) -> None:
        mock_client = MagicMock()
        # 60MB photo (limit 50MB)
        mock_client.head_object.return_value = {
            "ContentType": "image/jpeg",
            "ContentLength": 60 * 1024 * 1024,
        }
        with patch("pawguard.services.storage_service.boto3.client", return_value=mock_client):
            svc = StorageService()

            with pytest.raises(ValidationFailedError, match="exceeds the maximum 50MB limit"):
                svc.validate_report_media(photo_keys=["lost-found/huge.jpg"], video_key=None)

    def test_oversized_video_raises(self) -> None:
        mock_client = MagicMock()
        # 120MB video (limit 100MB)
        mock_client.head_object.return_value = {
            "ContentType": "video/mp4",
            "ContentLength": 120 * 1024 * 1024,
        }
        with patch("pawguard.services.storage_service.boto3.client", return_value=mock_client):
            svc = StorageService()

            with pytest.raises(ValidationFailedError, match="exceeds the maximum 100MB limit"):
                svc.validate_report_media(photo_keys=[], video_key="lost-found/huge.mp4")


class TestReportSchemaValidation:
    """Test schema level constraints and validators for lost, found, and rescue reports."""

    def test_lost_report_create_schema_validations(self) -> None:
        # Valid payload with multi-media
        payload = LostReportCreate(
            pet_name="Buddy",
            breed="Beagle",
            color="Brown",
            location_address="123 Street",
            lost_at="2026-08-27T12:00:00Z",
            photo_object_keys=["lost-found/p1.jpg", "lost-found/p2.jpg"],
            video_object_key="lost-found/v1.mp4",
        )
        assert payload.photo_object_keys == ["lost-found/p1.jpg", "lost-found/p2.jpg"]
        assert payload.video_object_key == "lost-found/v1.mp4"

        # Invalid photo prefix
        with pytest.raises(ValueError, match="expected prefix 'lost-found/'"):
            LostReportCreate(
                pet_name="Buddy",
                breed="Beagle",
                color="Brown",
                location_address="123 Street",
                lost_at="2026-08-27T12:00:00Z",
                photo_object_keys=["invalid/prefix.jpg"],
            )

    def test_found_report_create_schema_validations(self) -> None:
        # Valid payload
        payload = FoundReportCreate(
            breed_observed="Stray",
            color_observed="Black",
            location_address="Park Ave",
            found_at="2026-08-27T12:00:00Z",
            photo_object_keys=["lost-found/f1.png"],
        )
        assert payload.photo_object_keys == ["lost-found/f1.png"]

    def test_rescue_request_create_schema_validations(self) -> None:
        # Valid payload
        payload = RescueRequestCreate(
            reporter_name="John Doe",
            reporter_phone="+1234567890",
            location_address="Sector 5",
            physical_condition=RescuePhysicalCondition.INJURED,
            photo_object_keys=["rescue/r1.webp"],
            video_object_key="rescue/v1.mp4",
        )
        assert payload.photo_object_keys == ["rescue/r1.webp"]
        assert payload.video_object_key == "rescue/v1.mp4"
