"""Generic audit trail writer, reused by auth and every future domain module."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.auth.models import AuthAuditEventType, AuthAuditLog


def _jsonable(value: Any) -> Any:
    """Recursively coerce values into JSON-safe primitives for JSONB columns.

    UUIDs (and StrEnum/bytes) cannot be serialized to Postgres JSONB by the
    asyncpg driver; stringify them so audit metadata / state snapshots that
    embed entity IDs persist instead of raising a 500.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return value


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
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
    ) -> AuthAuditLog:
        entry = AuthAuditLog(
            user_id=actor_id,
            event_type=event_type.value,
            ip_address=ip_address,
            user_agent=user_agent,
            event_metadata=_jsonable(metadata),
            before_state=_jsonable(before_state),
            after_state=_jsonable(after_state),
        )
        self._session.add(entry)
        return entry
