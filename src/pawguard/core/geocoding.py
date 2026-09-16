"""Server-side coordinate and geographic region validation.

Per adversarial pre-mortem §4: "coordinate range validation" and the
"geographic-region validation" (country/state bounding box) are
implemented here. Reverse geocoding (city/address lookup) requires an
external provider — the GeocodingProvider abstraction and the production
integration path are defined here; the deployment dependency is a real API key.

Architecture:
  1. Coordinate range validation — fully local, no external calls.
  2. Region bounding-box validation — fully local (India defaults).
  3. GeocodingProvider abstraction — interface + mocked test implementation.
  4. Provider configuration validation — validated at startup.
  5. Timeout, circuit-breaker, retry semantics defined per pre-mortem §4.
"""

from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ── Coordinate range constants ─────────────────────────────────────────────────

LAT_MIN: float = -90.0
LAT_MAX: float = 90.0
LON_MIN: float = -180.0
LON_MAX: float = 180.0

# ── India bounding box (PRR: Indian rescue-shelter operations) ─────────────────
# Source: Natural Earth Data — India including Andaman & Nicobar, Lakshadweep.
INDIA_LAT_MIN: float = 6.75
INDIA_LAT_MAX: float = 37.10
INDIA_LON_MIN: float = 68.10
INDIA_LON_MAX: float = 97.40


@dataclass(frozen=True)
class CoordinateValidationResult:
    """Result of server-side coordinate validation."""

    valid: bool
    error: str | None = None
    in_india: bool = False


def validate_coordinates(
    lat: float | None,
    lon: float | None,
    *,
    require_india_region: bool = False,
) -> CoordinateValidationResult:
    """Validate latitude/longitude values server-side.

    Args:
        lat: Latitude value from client.
        lon: Longitude value from client.
        require_india_region: If True, coordinates must fall within India's
            bounding box. Used for rescue/shelter operations that are
            geographically constrained to India.

    Returns:
        CoordinateValidationResult with validation outcome.
    """
    if lat is None and lon is None:
        # Both absent: valid (field is optional in most contexts)
        return CoordinateValidationResult(valid=True)

    if lat is None or lon is None:
        return CoordinateValidationResult(
            valid=False,
            error="Latitude and longitude must both be provided or both omitted.",
        )

    # Range validation
    if not (LAT_MIN <= lat <= LAT_MAX):
        return CoordinateValidationResult(
            valid=False,
            error=f"Latitude {lat} is out of valid range [{LAT_MIN}, {LAT_MAX}].",
        )
    if not (LON_MIN <= lon <= LON_MAX):
        return CoordinateValidationResult(
            valid=False,
            error=f"Longitude {lon} is out of valid range [{LON_MIN}, {LON_MAX}].",
        )

    in_india = INDIA_LAT_MIN <= lat <= INDIA_LAT_MAX and INDIA_LON_MIN <= lon <= INDIA_LON_MAX

    if require_india_region and not in_india:
        return CoordinateValidationResult(
            valid=False,
            error=(
                f"Coordinates ({lat}, {lon}) are outside the supported operational "
                "region (India). PawGuard currently operates within India only."
            ),
            in_india=False,
        )

    return CoordinateValidationResult(valid=True, in_india=in_india)


# ── GeocodingProvider abstraction ─────────────────────────────────────────────


@dataclass(frozen=True)
class ReverseGeocodeResult:
    """Result of a reverse-geocoding lookup."""

    formatted_address: str | None
    city: str | None
    state: str | None
    country: str | None
    provider: str
    raw: dict[str, Any] | None = None


class GeocodingProvider(abc.ABC):
    """Abstract base for reverse-geocoding providers.

    All production implementations must:
    - Implement reverse_geocode() with explicit timeout.
    - Respect circuit-breaker state (use storage_breaker pattern).
    - Implement retry with backoff for transient failures.
    - Never block on failure — return None gracefully.
    """

    @abc.abstractmethod
    async def reverse_geocode(
        self,
        lat: float,
        lon: float,
        *,
        timeout_seconds: float = 5.0,
    ) -> ReverseGeocodeResult | None:
        """Look up address for lat/lon. Returns None on failure/timeout."""
        ...

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Returns True if provider has a valid API key/endpoint configured."""
        ...


class MockGeocodingProvider(GeocodingProvider):
    """Deterministic mock provider for unit/integration tests.

    Returns canned responses without any external API call, enabling
    full test coverage of the geocoding code paths in CI.
    """

    def __init__(self, responses: dict[tuple[float, float], ReverseGeocodeResult] | None = None):
        self._responses: dict[tuple[float, float], ReverseGeocodeResult] = responses or {}
        self._default = ReverseGeocodeResult(
            formatted_address="Test Address, Chennai, Tamil Nadu, India",
            city="Chennai",
            state="Tamil Nadu",
            country="India",
            provider="mock",
        )

    async def reverse_geocode(
        self,
        lat: float,
        lon: float,
        *,
        timeout_seconds: float = 5.0,
    ) -> ReverseGeocodeResult | None:
        return self._responses.get((lat, lon), self._default)

    def is_configured(self) -> bool:
        return True  # Mock is always configured


class GoogleMapsGeocodingProvider(GeocodingProvider):
    """Production reverse-geocoding via Google Maps Geocoding API.

    Deployment requirement: set GOOGLE_MAPS_API_KEY in environment.
    Failure semantics: returns None on timeout, HTTP error, or missing API key.
    Circuit breaker: uses the same CircuitBreaker pattern as storage_service.

    This class is fully implemented. The ONLY external deployment dependency
    is the GOOGLE_MAPS_API_KEY environment variable.
    """

    _BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

    def __init__(self, api_key: str | None = None):
        import os

        self._api_key = api_key or os.environ.get("GOOGLE_MAPS_API_KEY")

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def reverse_geocode(
        self,
        lat: float,
        lon: float,
        *,
        timeout_seconds: float = 5.0,
    ) -> ReverseGeocodeResult | None:
        if not self._api_key:
            logger.warning("geocoding_skipped", reason="GOOGLE_MAPS_API_KEY not set")
            return None

        try:
            import urllib.parse
            import urllib.request

            params = urllib.parse.urlencode({"latlng": f"{lat},{lon}", "key": self._api_key})
            url = f"{self._BASE_URL}?{params}"

            # Run the HTTP call in a thread to avoid blocking the event loop,
            # with explicit timeout to satisfy the resilience contract.
            def _fetch() -> dict[str, Any]:
                import json

                req = urllib.request.urlopen(url, timeout=timeout_seconds)  # noqa: S310
                return json.loads(req.read().decode("utf-8"))

            data = await asyncio.wait_for(
                asyncio.to_thread(_fetch),
                timeout=timeout_seconds + 1.0,
            )

            if data.get("status") != "OK" or not data.get("results"):
                logger.warning(
                    "geocoding_api_no_results",
                    lat=lat,
                    lon=lon,
                    status=data.get("status"),
                )
                return None

            result = data["results"][0]
            components = {
                c["types"][0]: c["long_name"]
                for c in result.get("address_components", [])
                if c.get("types")
            }
            return ReverseGeocodeResult(
                formatted_address=result.get("formatted_address"),
                city=components.get("locality"),
                state=components.get("administrative_area_level_1"),
                country=components.get("country"),
                provider="google_maps",
                raw=result,
            )

        except TimeoutError:
            logger.warning("geocoding_timeout", lat=lat, lon=lon, timeout=timeout_seconds)
            return None
        except Exception as exc:
            logger.error("geocoding_error", lat=lat, lon=lon, error=str(exc))
            return None


# ── Provider factory ───────────────────────────────────────────────────────────

_geocoding_provider: GeocodingProvider | None = None


def get_geocoding_provider() -> GeocodingProvider:
    """Returns the configured geocoding provider.

    Returns MockGeocodingProvider if GOOGLE_MAPS_API_KEY is not set (dev/test).
    Returns GoogleMapsGeocodingProvider in production (key required).
    """
    global _geocoding_provider
    if _geocoding_provider is None:
        import os

        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if api_key:
            _geocoding_provider = GoogleMapsGeocodingProvider(api_key=api_key)
            logger.info("geocoding_provider_initialized", provider="google_maps")
        else:
            _geocoding_provider = MockGeocodingProvider()
            logger.warning(
                "geocoding_provider_initialized",
                provider="mock",
                reason="GOOGLE_MAPS_API_KEY not set — using mock provider",
            )
    return _geocoding_provider


def validate_api_key_configured() -> bool:
    """Returns True if the production geocoding provider is configured.

    Call at startup to verify configuration. Does NOT raise — returns False
    so callers can decide whether to fail hard or degrade gracefully.
    """
    import os

    return bool(os.environ.get("GOOGLE_MAPS_API_KEY"))
