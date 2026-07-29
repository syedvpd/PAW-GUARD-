"""DashboardRepository: handles data access for admin dashboard metrics."""

from sqlalchemy import select, func

from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.auth.models import User, Role, RefreshToken


class DashboardRepository:
    def __init__(self, session: AsyncSessionLocal) -> None:
        self._session = session

    async def get_total_users_count(self) -> int:
        result = await self._session.execute(select(func.count(User.id)))
        return result.scalar_one()

    async def get_active_users_count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(User).where(User.is_active == True))
        return result.scalar_one()

    async def get_total_roles_count(self) -> int:
        result = await self._session.execute(select(func.count(Role.id)))
        return result.scalar_one()

    async def get_active_sessions_count(self) -> int:
        result = await self._session.execute(select(func.count(RefreshToken.id)).where(RefreshToken.is_revoked == False))
        return result.scalar_one()