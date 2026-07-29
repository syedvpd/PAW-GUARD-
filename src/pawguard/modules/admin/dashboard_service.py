"""DashboardService: owns all admin dashboard business behaviour (RULE-003)."""

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
