"""Generic audit trail writer, reused by auth and every future domain module."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.auth.models import AuthAuditEventType, AuthAuditLog


class AuditService:
    """Writes to `auth_audit_logs`. A generic cross-module `audit_logs` table can be added
    when non-auth domains need auditing — this stays auth-scoped for Phase 1."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        event_type: AuthAuditEventType,
        actor_id: uuid.UUID | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuthAuditLog:
        entry = AuthAuditLog(
            user_id=actor_id,
            event_type=event_type.value,
            ip_address=ip_address,
            user_agent=user_agent,
            event_metadata=metadata,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry
