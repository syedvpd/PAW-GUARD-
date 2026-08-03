"""Unit tests for core/upload.py batch size enforcement."""

import pytest

from pawguard.core.upload import UploadError, verify_batch_size


class TestVerifyBatchSize:
    def test_batch_under_limit_passes(self):
        verify_batch_size([1024, 2048, 512])

    def test_batch_at_limit_passes(self):
        verify_batch_size([50 * 1024 * 1024])

    def test_batch_exceeds_limit_raises(self):
        with pytest.raises(UploadError, match="exceeds the 50 MB limit"):
            verify_batch_size([30 * 1024 * 1024, 25 * 1024 * 1024])

    def test_empty_batch_passes(self):
        verify_batch_size([])

    def test_single_large_file_raises(self):
        with pytest.raises(UploadError, match="exceeds the 50 MB limit"):
            verify_batch_size([51 * 1024 * 1024])

    def test_exact_limit_passes(self):
        verify_batch_size([25 * 1024 * 1024, 25 * 1024 * 1024])