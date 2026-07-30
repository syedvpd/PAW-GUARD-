"""DashboardService: aggregates data across all modules for admin dashboard (RULE-003)."""

from typing import Any

from pawguard.modules.admin.dashboard_repository import DashboardRepository


class DashboardService:
    def __init__(self, repository: DashboardRepository) -> None:
        self._repo = repository

    async def get_system_metrics(self) -> dict[str, int]:
        total_users = await self._repo.get_total_users_count()
        active_users = await self._repo.get_active_users_count()
        total_roles = await self._repo.get_total_roles_count()
        active_sessions = await self._repo.get_active_sessions_count()
        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_roles": total_roles,
            "active_sessions": active_sessions,
        }

    async def get_summary(self) -> dict[str, Any]:
        users = await self._repo.get_total_users_count()
        dogs = await self._repo.get_total_dogs_count()
        adoptable = await self._repo.get_adoptable_dogs_count()
        pending_adoptions = await self._repo.get_pending_adoptions_count()
        active_sessions = await self._repo.get_active_sessions_count()
        open_grievances = await self._repo.get_open_grievances()
        unread_notifications = await self._repo.get_unread_notifications_count()
        active_fosters = await self._repo.get_active_fosters()
        shelter = await self._repo.get_shelter_occupancy()
        verified_users = await self._repo.get_verified_users_count()

        return {
            "total_users": users,
            "verified_users": verified_users,
            "total_dogs": dogs,
            "adoptable_dogs": adoptable,
            "pending_adoptions": pending_adoptions,
            "active_sessions": active_sessions,
            "open_grievances": open_grievances,
            "unread_notifications": unread_notifications,
            "active_foster_placements": active_fosters,
            "shelter_occupancy": shelter,
        }

    async def get_kpis(self) -> dict[str, Any]:
        rescue_kpis = await self._repo.get_rescue_kpis()
        donation_totals = await self._repo.get_donation_totals()
        adoption_rate = await self._repo.get_adoption_rate()
        volunteer_hours = await self._repo.get_volunteer_hours()
        feedback = await self._repo.get_feedback_summary()

        return {
            "rescue_kpis": rescue_kpis,
            "donation_totals": donation_totals,
            "adoption_rate_pct": adoption_rate,
            "total_volunteer_hours": volunteer_hours,
            "feedback": feedback,
        }

    async def get_charts(self) -> dict[str, Any]:
        adoption_trend = await self._repo.get_monthly_adoption_trend()
        rescue_trend = await self._repo.get_monthly_rescue_trend()
        donation_trend = await self._repo.get_monthly_donation_trend()
        breed_distribution = await self._repo.get_dog_breed_distribution()

        return {
            "adoption_trend": adoption_trend,
            "rescue_trend": rescue_trend,
            "donation_trend": donation_trend,
            "breed_distribution": breed_distribution,
        }

    async def get_recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._repo.get_recent_activity(limit=limit)

    async def get_inventory_alerts(self) -> dict[str, Any]:
        alerts = await self._repo.get_inventory_alerts()
        expiring = await self._repo.count_expiring_inventory(days=30)
        return {"low_stock_items": alerts, "expiring_within_30_days": expiring}

    async def get_donation_summary(self) -> dict[str, Any]:
        totals = await self._repo.get_donation_totals()
        recent = await self._repo.get_recent_donations(days=30)
        return {"all_time": totals, "last_30_days": recent}

    async def get_rescue_stats(self) -> dict[str, Any]:
        kpis = await self._repo.get_rescue_kpis()
        by_status = await self._repo.count_rescues_by_status()
        return {"kpis": kpis, "by_status": by_status}

    async def get_medical_stats(self) -> dict[str, Any]:
        return await self._repo.get_medical_stats()

    async def get_adoption_stats(self) -> dict[str, Any]:
        by_status = await self._repo.count_adoptions_by_status()
        rate = await self._repo.get_adoption_rate()
        return {"by_status": by_status, "adoption_rate_pct": rate}

    async def get_volunteer_stats(self) -> dict[str, Any]:
        by_status = await self._repo.count_volunteers_by_status()
        hours = await self._repo.get_volunteer_hours()
        return {"by_status": by_status, "total_hours_logged": hours}

    async def get_notification_summary(self) -> dict[str, Any]:
        unread = await self._repo.get_unread_notifications_count()
        return {"unread_count": unread}

    async def get_shelter_stats(self) -> dict[str, Any]:
        occupancy = await self._repo.get_shelter_occupancy()
        dogs_by_status = await self._repo.count_dogs_by_status()
        return {"occupancy": occupancy, "dogs_by_status": dogs_by_status}

    async def get_foster_stats(self) -> dict[str, Any]:
        return await self._repo.get_foster_stats()

    async def get_lost_found_stats(self) -> dict[str, Any]:
        return await self._repo.get_active_lost_found()

    async def get_grievance_stats(self) -> dict[str, Any]:
        by_status = await self._repo.count_grievances_by_status()
        feedback = await self._repo.get_feedback_summary()
        return {"by_status": by_status, "feedback": feedback}
