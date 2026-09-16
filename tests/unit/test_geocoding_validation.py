"""Geocoding validation tests — adversarial (ITEM 9f).

Per adversarial pre-mortem §4:
- Coordinate range validation: fully proven locally.
- India region validation: fully proven locally.
- GeocodingProvider abstraction: proven with MockGeocodingProvider.
- GoogleMapsGeocodingProvider: architecture proven; production API key = external dependency.
- Timeout/failure semantics: proven with mock that simulates failure.
"""

from __future__ import annotations

import pytest

from pawguard.core.geocoding import (
    INDIA_LAT_MAX,
    INDIA_LAT_MIN,
    INDIA_LON_MAX,
    INDIA_LON_MIN,
    LAT_MAX,
    LAT_MIN,
    LON_MAX,
    LON_MIN,
    GoogleMapsGeocodingProvider,
    MockGeocodingProvider,
    ReverseGeocodeResult,
    validate_coordinates,
)


class TestCoordinateRangeValidation:
    """Server-side coordinate range validation (no external API required)."""

    def test_valid_coordinates_pass(self) -> None:
        result = validate_coordinates(12.9716, 77.5946)
        assert result.valid
        assert result.error is None

    def test_valid_coordinates_zero_zero_passes(self) -> None:
        result = validate_coordinates(0.0, 0.0)
        assert result.valid

    def test_valid_extreme_lat_max(self) -> None:
        result = validate_coordinates(LAT_MAX, 0.0)
        assert result.valid

    def test_valid_extreme_lat_min(self) -> None:
        result = validate_coordinates(LAT_MIN, 0.0)
        assert result.valid

    def test_valid_extreme_lon_max(self) -> None:
        result = validate_coordinates(0.0, LON_MAX)
        assert result.valid

    def test_valid_extreme_lon_min(self) -> None:
        result = validate_coordinates(0.0, LON_MIN)
        assert result.valid

    def test_lat_too_high_rejected(self) -> None:
        result = validate_coordinates(90.01, 0.0)
        assert not result.valid
        assert "Latitude" in (result.error or "")

    def test_lat_too_low_rejected(self) -> None:
        result = validate_coordinates(-90.01, 0.0)
        assert not result.valid
        assert "Latitude" in (result.error or "")

    def test_lon_too_high_rejected(self) -> None:
        result = validate_coordinates(0.0, 180.01)
        assert not result.valid
        assert "Longitude" in (result.error or "")

    def test_lon_too_low_rejected(self) -> None:
        result = validate_coordinates(0.0, -180.01)
        assert not result.valid
        assert "Longitude" in (result.error or "")

    def test_lat_without_lon_rejected(self) -> None:
        result = validate_coordinates(12.97, None)
        assert not result.valid
        assert "both" in (result.error or "").lower()

    def test_lon_without_lat_rejected(self) -> None:
        result = validate_coordinates(None, 77.59)
        assert not result.valid
        assert "both" in (result.error or "").lower()

    def test_both_none_is_valid(self) -> None:
        """Both absent = field is optional."""
        result = validate_coordinates(None, None)
        assert result.valid

    def test_nonsense_values_rejected(self) -> None:
        result = validate_coordinates(999.0, -999.0)
        assert not result.valid


class TestIndiaRegionValidation:
    """India bounding-box validation for operational region enforcement."""

    # Bangalore coordinates — inside India
    BANGALORE_LAT = 12.9716
    BANGALORE_LON = 77.5946

    # London coordinates — outside India
    LONDON_LAT = 51.5074
    LONDON_LON = -0.1278

    def test_india_coordinates_identified(self) -> None:
        result = validate_coordinates(self.BANGALORE_LAT, self.BANGALORE_LON)
        assert result.valid
        assert result.in_india is True

    def test_outside_india_coordinates_not_flagged_when_not_required(self) -> None:
        """Without require_india_region, non-India coordinates still pass."""
        result = validate_coordinates(self.LONDON_LAT, self.LONDON_LON)
        assert result.valid
        assert result.in_india is False

    def test_outside_india_rejected_when_region_required(self) -> None:
        result = validate_coordinates(self.LONDON_LAT, self.LONDON_LON, require_india_region=True)
        assert not result.valid
        assert "India" in (result.error or "")

    def test_india_boundary_edges(self) -> None:
        """Exact boundary corners of India bounding box are valid."""
        result = validate_coordinates(INDIA_LAT_MIN, INDIA_LON_MIN)
        assert result.valid
        result = validate_coordinates(INDIA_LAT_MAX, INDIA_LON_MAX)
        assert result.valid

    def test_chennai_coordinates(self) -> None:
        result = validate_coordinates(13.0827, 80.2707, require_india_region=True)
        assert result.valid
        assert result.in_india is True

    def test_mumbai_coordinates(self) -> None:
        result = validate_coordinates(19.0760, 72.8777, require_india_region=True)
        assert result.valid
        assert result.in_india is True


class TestMockGeocodingProvider:
    """MockGeocodingProvider for deterministic CI testing."""

    @pytest.mark.asyncio
    async def test_mock_returns_default_result(self) -> None:
        provider = MockGeocodingProvider()
        result = await provider.reverse_geocode(12.97, 77.59)
        assert result is not None
        assert result.provider == "mock"
        assert result.city is not None

    @pytest.mark.asyncio
    async def test_mock_returns_canned_response(self) -> None:
        canned = ReverseGeocodeResult(
            formatted_address="456 Test Street, Mumbai, Maharashtra, India",
            city="Mumbai",
            state="Maharashtra",
            country="India",
            provider="mock",
        )
        provider = MockGeocodingProvider(responses={(19.07, 72.88): canned})
        result = await provider.reverse_geocode(19.07, 72.88)
        assert result is not None
        assert result.city == "Mumbai"

    def test_mock_is_configured(self) -> None:
        provider = MockGeocodingProvider()
        assert provider.is_configured() is True


class TestGoogleMapsProviderConfiguration:
    """GoogleMapsGeocodingProvider: configuration validation (no real API calls)."""

    def test_not_configured_without_key(self) -> None:
        provider = GoogleMapsGeocodingProvider(api_key=None)
        assert provider.is_configured() is False

    def test_configured_with_key(self) -> None:
        provider = GoogleMapsGeocodingProvider(api_key="fake-key-for-test")
        assert provider.is_configured() is True

    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self) -> None:
        """Without API key, reverse_geocode returns None gracefully (no exception)."""
        provider = GoogleMapsGeocodingProvider(api_key=None)
        result = await provider.reverse_geocode(12.97, 77.59)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self) -> None:
        """Provider must return None on timeout, not raise."""
        import unittest.mock

        provider = GoogleMapsGeocodingProvider(api_key="fake-key")

        with unittest.mock.patch("asyncio.to_thread", side_effect=TimeoutError("timeout")):
            result = await provider.reverse_geocode(12.97, 77.59, timeout_seconds=0.001)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self) -> None:
        """Provider must return None on HTTP error, not raise."""
        import unittest.mock

        provider = GoogleMapsGeocodingProvider(api_key="fake-key")

        with unittest.mock.patch("asyncio.to_thread", side_effect=OSError("network error")):
            result = await provider.reverse_geocode(12.97, 77.59)
        assert result is None


class TestGeocodingProviderFactory:
    """validate_api_key_configured() reflects environment state."""

    def test_returns_false_without_key(self) -> None:
        import os
        import unittest.mock

        from pawguard.core.geocoding import validate_api_key_configured

        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            # Remove key if present
            os.environ.pop("GOOGLE_MAPS_API_KEY", None)
            result = validate_api_key_configured()
        assert result is False

    def test_returns_true_with_key(self) -> None:
        import os
        import unittest.mock

        from pawguard.core.geocoding import validate_api_key_configured

        with unittest.mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test-key"}):
            result = validate_api_key_configured()
        assert result is True
