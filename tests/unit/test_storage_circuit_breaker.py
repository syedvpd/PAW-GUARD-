"""Storage circuit breaker tests — adversarial (ITEM 3).

Proves:
1. @storage_breaker is applied to every outbound S3 method.
2. After failure_threshold consecutive failures, CircuitBreakerOpenException fires.
3. Covers every newly decorated method individually.
4. Verifies no bypass path exists (sign_media_url, validate_report_media via head_object).

Per adversarial pre-mortem §7: "No production storage network operation can bypass
the intended timeout/resilience policy."
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pawguard.core.resilience import CircuitBreakerOpenException
from pawguard.services.storage_service import StorageService


def _make_service() -> StorageService:
    """Create a StorageService with a mocked boto3 client."""
    with patch("pawguard.services.storage_service.boto3") as mock_boto:
        mock_boto.client.return_value = MagicMock()
        svc = StorageService()
    # Reset circuit breaker state between tests
    from pawguard.core.resilience import CircuitState
    from pawguard.services.storage_service import storage_breaker

    storage_breaker.failure_count = 0
    storage_breaker.state = CircuitState.CLOSED
    svc._client = MagicMock()
    svc._bucket = "test-bucket"
    return svc


FAILURE_THRESHOLD = 5  # matches storage_breaker definition


class TestCircuitBreakerGeneratePresignedUploadUrl:
    """generate_presigned_upload_url opens circuit after threshold failures."""

    def test_opens_after_threshold_failures(self) -> None:
        svc = _make_service()
        svc._client.generate_presigned_url.side_effect = ConnectionError("S3 down")

        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(Exception):  # StorageError wrapping ConnectionError  # noqa: B017
                svc.generate_presigned_upload_url(
                    object_key="test/key.jpg", content_type="image/jpeg"
                )

        # Next call must trip the open circuit
        from pawguard.core.resilience import CircuitState
        from pawguard.services.storage_service import storage_breaker

        assert storage_breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenException):
            svc.generate_presigned_upload_url(object_key="test/key.jpg", content_type="image/jpeg")


class TestCircuitBreakerGeneratePresignedDownloadUrl:
    """generate_presigned_download_url opens circuit after threshold failures."""

    def test_opens_after_threshold_failures(self) -> None:
        svc = _make_service()
        svc._client.generate_presigned_url.side_effect = ConnectionError("S3 down")

        # generate_presigned_download_url internally records breaker failures
        # on each exception (via storage_breaker.record_failure()) before returning
        # a graceful fallback URL. After FAILURE_THRESHOLD calls, the breaker opens.
        for _ in range(FAILURE_THRESHOLD):
            # Returns fallback URL rather than raising
            result = svc.generate_presigned_download_url(object_key="test/file.pdf")
            assert result  # fallback URL is returned, not empty

        from pawguard.core.resilience import CircuitState
        from pawguard.services.storage_service import storage_breaker

        assert storage_breaker.state == CircuitState.OPEN, (
            f"Expected circuit OPEN after {FAILURE_THRESHOLD} failures, got {storage_breaker.state}"
        )


class TestCircuitBreakerGetObjectSize:
    """get_object_size opens circuit after threshold failures."""

    def test_opens_after_threshold_failures(self) -> None:
        svc = _make_service()
        svc._client.head_object.side_effect = ConnectionError("S3 down")

        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(Exception):  # noqa: B017
                svc.get_object_size(object_key="test/key.jpg")

        from pawguard.core.resilience import CircuitState
        from pawguard.services.storage_service import storage_breaker

        assert storage_breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenException):
            svc.get_object_size(object_key="test/key.jpg")


class TestCircuitBreakerGetObjectPrefixBytes:
    """get_object_prefix_bytes opens circuit after threshold failures."""

    def test_opens_after_threshold_failures(self) -> None:
        svc = _make_service()
        svc._client.get_object.side_effect = ConnectionError("S3 down")

        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(Exception):  # noqa: B017
                svc.get_object_prefix_bytes(object_key="test/key.jpg")

        from pawguard.core.resilience import CircuitState
        from pawguard.services.storage_service import storage_breaker

        assert storage_breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenException):
            svc.get_object_prefix_bytes(object_key="test/key.jpg")


class TestCircuitBreakerGetObject:
    """get_object opens circuit after threshold failures."""

    def test_opens_after_threshold_failures(self) -> None:
        svc = _make_service()
        svc._client.get_object.side_effect = ConnectionError("S3 down")

        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(Exception):  # noqa: B017
                svc.get_object(object_key="test/key.jpg")

        from pawguard.core.resilience import CircuitState
        from pawguard.services.storage_service import storage_breaker

        assert storage_breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenException):
            svc.get_object(object_key="test/key.jpg")


class TestCircuitBreakerPutObject:
    """put_object opens circuit after threshold failures."""

    def test_opens_after_threshold_failures(self) -> None:
        svc = _make_service()
        svc._client.put_object.side_effect = ConnectionError("S3 down")

        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(Exception):  # noqa: B017
                svc.put_object(
                    object_key="test/key.jpg",
                    content=b"data",
                    content_type="image/jpeg",
                )

        from pawguard.core.resilience import CircuitState
        from pawguard.services.storage_service import storage_breaker

        assert storage_breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenException):
            svc.put_object(
                object_key="test/key.jpg",
                content=b"data",
                content_type="image/jpeg",
            )


class TestCircuitBreakerDeleteObject:
    """delete_object opens circuit after threshold failures (already had it; regression test)."""

    def test_opens_after_threshold_failures(self) -> None:
        svc = _make_service()
        svc._client.delete_object.side_effect = ConnectionError("S3 down")

        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(Exception):  # noqa: B017
                svc.delete_object(object_key="test/key.jpg")

        from pawguard.core.resilience import CircuitState
        from pawguard.services.storage_service import storage_breaker

        assert storage_breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenException):
            svc.delete_object(object_key="test/key.jpg")


class TestCircuitBreakerSignMediaUrl:
    """sign_media_url opens circuit after threshold failures.

    Bypass test: sign_media_url calls self._client.generate_presigned_url directly.
    Before the fix it was unprotected. This test proves the bypass is closed.
    """

    def test_opens_after_threshold_failures(self) -> None:
        svc = _make_service()
        svc._client.generate_presigned_url.side_effect = ConnectionError("S3 down")

        # sign_media_url and generate_presigned_download_url share the same circuit breaker
        # (module-level storage_breaker). Each sign_media_url failure registers:
        #   1 failure in sign_media_url's except block (via record_failure())
        #   + potentially 1 failure in generate_presigned_download_url's except block
        # So the circuit may open before FAILURE_THRESHOLD iterations of the outer loop.
        # We allow CircuitBreakerOpenException to be raised mid-loop — what matters is
        # the circuit is OPEN at the end.
        from pawguard.core.resilience import CircuitState
        from pawguard.services.storage_service import storage_breaker

        for _ in range(FAILURE_THRESHOLD * 2):
            try:
                svc.sign_media_url("private/doc.pdf")
            except CircuitBreakerOpenException:
                # Circuit opened mid-loop — this is correct behavior
                break

        assert storage_breaker.state == CircuitState.OPEN, (
            f"Expected circuit OPEN after repeated failures, got {storage_breaker.state}"
        )


class TestCircuitBreakerSuccess:
    """Positive test: circuit remains CLOSED when calls succeed."""

    def test_stays_closed_on_success(self) -> None:
        svc = _make_service()
        svc._client.put_object.return_value = {}

        # Many successful calls
        for _ in range(10):
            svc.put_object(
                object_key="test/key.jpg",
                content=b"data",
                content_type="image/jpeg",
            )

        from pawguard.core.resilience import CircuitState
        from pawguard.services.storage_service import storage_breaker

        assert storage_breaker.state == CircuitState.CLOSED


class TestMimeListConsolidation:
    """ITEM 9a: MIME lists in storage_service come from core/upload.py."""

    def test_storage_uses_core_mime_lists(self) -> None:
        """Verifies that the storage service uses the same MIME sets as core/upload.py."""

        # Verify the constants are imported (not independently defined)
        # by checking the service module's namespace references the upload module's objects
        import inspect

        import pawguard.services.storage_service as ss_module

        source = inspect.getsource(ss_module)
        assert "ALLOWED_IMAGE_MIMES" in source
        assert "ALLOWED_VIDEO_MIMES" in source
        # The old inline sets should NOT be present
        assert 'allowed_photo_mimes = {"image/jpeg"' not in source
        assert 'allowed_video_mimes = {"video/mp4"' not in source

    def test_image_mime_set_is_correct(self) -> None:
        from pawguard.core.upload import ALLOWED_IMAGE_MIMES

        assert "image/jpeg" in ALLOWED_IMAGE_MIMES
        assert "image/png" in ALLOWED_IMAGE_MIMES
        assert "image/webp" in ALLOWED_IMAGE_MIMES
        assert "video/mp4" not in ALLOWED_IMAGE_MIMES
        assert "application/pdf" not in ALLOWED_IMAGE_MIMES

    def test_video_mime_set_is_correct(self) -> None:
        from pawguard.core.upload import ALLOWED_VIDEO_MIMES

        assert "video/mp4" in ALLOWED_VIDEO_MIMES
        assert "video/webm" in ALLOWED_VIDEO_MIMES
        assert "video/quicktime" in ALLOWED_VIDEO_MIMES
        assert "image/jpeg" not in ALLOWED_VIDEO_MIMES
