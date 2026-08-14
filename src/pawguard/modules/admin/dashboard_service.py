"""DashboardService: aggregates data across all modules for admin dashboard (RULE-003)."""

from contextlib import suppress
from typing import Any

from pawguard.modules.admin.dashboard_repository import DashboardRepository
from pawguard.redis.client import RedisClient
from pawguard.services.cache_service import CacheService

# Admin overview metrics are read-heavy aggregates. A short TTL absorbs the
# repeated polling typical of dashboard UIs without serving stale data for long.
ADMIN_DASHBOARD_TTL = 30  # seconds


class DashboardService:
    def __init__(self, repository: DashboardRepository, redis: RedisClient | None = None) -> None:
        self._repo = repository
        self._redis = redis

    async def _cached(self, key: str, producer) -> Any:
        """Return cached aggregate when Redis is available, else compute fresh.

        Caching is best-effort: a missing/unavailable Redis or a failed write
        must never turn a dashboard read into an error (CACHE CONTRACT).
        """
        if self._redis is None:
            return await producer()
        cache = CacheService(self._redis, namespace="admin_dashboard")
        try:
            cached = await cache.get(key)
        except Exception:
            cached = None
        if cached is not None:
            return cached
        data = await producer()
        with suppress(Exception):
            await cache.set(key, data, ttl_seconds=ADMIN_DASHBOARD_TTL)
        return data

    async def get_system_metrics(self) -> dict[str, int]:
        return await self._cached("system_metrics", self._repo.get_system_metrics)

    async def get_summary(self) -> dict[str, Any]:
        return await self._cached("summary", self._repo.get_summary)

    async def get_kpis(self) -> dict[str, Any]:
        return await self._cached("kpis", self._repo.get_kpis)

    async def get_charts(self) -> dict[str, Any]:
        return await self._cached("charts", self._repo.get_charts)

    async def get_recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._cached(
            f"recent_activity:{limit}",
            lambda: self._repo.get_recent_activity(limit=limit),
        )

    async def get_inventory_alerts(self) -> dict[str, Any]:
        return await self._cached("inventory_alerts", self._repo.get_inventory_alerts)

    async def get_donation_summary(self) -> dict[str, Any]:
        return await self._cached("donation_summary", self._repo.get_donation_summary)

    async def get_rescue_stats(self) -> dict[str, Any]:
        return await self._cached("rescue_stats", self._repo.get_rescue_stats)

    async def get_medical_stats(self) -> dict[str, Any]:
        return await self._cached("medical_stats", self._repo.get_medical_stats)

    async def get_adoption_stats(self) -> dict[str, Any]:
        return await self._cached("adoption_stats", self._repo.get_adoption_stats)

    async def get_volunteer_stats(self) -> dict[str, Any]:
        return await self._cached("volunteer_stats", self._repo.get_volunteer_stats)

    async def get_notification_summary(self) -> dict[str, Any]:
        return await self._cached("notification_summary", self._repo.get_notification_summary)

    async def get_shelter_stats(self) -> dict[str, Any]:
        return await self._cached("shelter_stats", self._repo.get_shelter_stats)

    async def get_foster_stats(self) -> dict[str, Any]:
        return await self._cached("foster_stats", self._repo.get_foster_stats)

    async def get_lost_found_stats(self) -> dict[str, Any]:
        return await self._cached("lost_found_stats", self._repo.get_lost_found_stats)

    async def get_grievance_stats(self) -> dict[str, Any]:
        return await self._cached("grievance_stats", self._repo.get_grievance_stats)
