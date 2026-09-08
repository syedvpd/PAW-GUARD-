"""Background delivery jobs for lost-pet community alerts."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, literal, or_, select

from pawguard.core.config import get_settings
from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.auth.models import User
from pawguard.modules.lost_found.models import ReportStatus
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.schemas import BroadcastCreate
from pawguard.modules.notifications.service import NotificationService


def _distance_km(latitude: float, longitude: float) -> Any:
    """Haversine great-circle distance from a fixed point to ``User``, in SQL.

    Mirrors ShelterRepository.find_nearby_facilities so no PostGIS extension is
    needed on the managed Postgres hosting.
    """
    lat1 = func.radians(literal(latitude))
    lng1 = func.radians(literal(longitude))
    lat2 = func.radians(User.latitude)
    lng2 = func.radians(User.longitude)
    a_expr = func.pow(func.sin((lat2 - lat1) / 2), 2) + func.cos(lat1) * func.cos(lat2) * func.pow(
        func.sin((lng2 - lng1) / 2), 2
    )
    return 2 * literal(6371.0) * func.asin(func.sqrt(a_expr))


def recipient_stmt(
    exclude_user_id: uuid.UUID,
    latitude: float | None,
    longitude: float | None,
) -> Any:
    """Active users to alert about a lost report at ``latitude``/``longitude``.

    Scoped to ``lost_pet_broadcast_radius_km`` around the report. Users whose
    own coordinates are unknown stay in the fan-out: an alert that silently
    reaches nobody is worse than one that reaches too many, and the column is
    empty for every account until profiles start supplying it.
    """
    stmt = select(User.id).where(
        User.is_active.is_(True),
        User.deleted_at.is_(None),
        User.id != exclude_user_id,
    )
    if latitude is None or longitude is None:
        return stmt
    return stmt.where(
        or_(
            User.latitude.is_(None),
            User.longitude.is_(None),
            _distance_km(latitude, longitude) <= get_settings().lost_pet_broadcast_radius_km,
        )
    )


async def broadcast_lost_pet_alert(ctx: dict[str, Any], *, report_id: str, **_: Any) -> int:
    """Fan out one active lost report, exactly once, to nearby active users.

    Recipients are scoped to ``lost_pet_broadcast_radius_km`` around the
    report's pin — see :func:`recipient_stmt`. The row lock and
    ``broadcasted_at`` marker make ARQ retries and concurrent worker executions
    safe. Notifications are written in bounded batches. Also sends push
    notifications via FCM.
    """
    del ctx
    async with AsyncSessionLocal() as session:
        repository = LostFoundRepository(session)
        report = await repository.get_lost_report_for_broadcast(uuid.UUID(report_id))
        if report is None or report.status != ReportStatus.ACTIVE or report.broadcasted_at:
            return 0

        recipients = await session.execute(
            recipient_stmt(
                report.user_id,
                float(report.latitude) if report.latitude is not None else None,
                float(report.longitude) if report.longitude is not None else None,
            )
        )
        user_ids = list(recipients.scalars().all())
        notification_service = NotificationService(repository=NotificationRepository(session))
        payload = BroadcastCreate(
            title=f"Lost pet alert: {report.pet_name}",
            body=(
                f"{report.pet_name} was reported lost near {report.location_address}. "
                "Please check the alert and report a sighting if you can help."
            ),
            notification_type="lost_pet_alert",
            action_url=f"/api/v1/lost-found/lost/{report.id}",
        )
        sent = 0
        for offset in range(0, len(user_ids), 500):
            batch = user_ids[offset : offset + 500]
            await notification_service.broadcast(payload, batch)
            sent += len(batch)

        # Send push notifications to all recipients
        push_title = f"Lost pet alert: {report.pet_name}"
        push_body = (
            f"{report.pet_name} was reported lost near {report.location_address}. "
            "Please check the alert and report a sighting if you can help."
        )
        for offset in range(0, len(user_ids), 500):
            batch = user_ids[offset : offset + 500]
            await notification_service._send_push_to_users(
                batch,
                push_title,
                push_body,
                f"/api/v1/lost-found/lost/{report.id}",
            )

        report.broadcasted_at = datetime.now(UTC)
        await session.commit()
        return sent
