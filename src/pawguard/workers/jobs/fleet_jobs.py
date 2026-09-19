"""Scheduled background jobs for the fleet module (PRR 3.13).

These alert staff holding the fleet/vehicle permission when maintenance is
due, insurance is expiring, or checked-out equipment is overdue. They are
kept off the request path per TRANSACTION RULES and follow the same staff
notification pattern as ``scheduled_jobs.check_inventory_low_stock``.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, select

from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.auth import permission_codes as pc
from pawguard.modules.fleet.models import EquipmentCheckout, Vehicle
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.service import MAINTENANCE_DUE_WINDOW
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.schemas import NotificationCreate
from pawguard.modules.notifications.service import NotificationService
from pawguard.workers.jobs.scheduled_jobs import _staff_user_ids


async def check_fleet_maintenance_due(ctx: dict[str, object]) -> None:
    """Alert staff when a vehicle's latest service says the next one is due
    within 14 days or already overdue. Superseded records never alert."""
    cutoff = date.today() + MAINTENANCE_DUE_WINDOW

    async with AsyncSessionLocal() as session:
        due = await FleetRepository(session).list_maintenance_due(cutoff)

        if not due:
            return

        staff_user_ids = await _staff_user_ids(session, pc.VEHICLE_READ)
        if not staff_user_ids:
            return

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for vehicle, record in due:
            body = f"Vehicle {vehicle.license_plate} has maintenance due on {record.next_due_date}."
            for user_id in staff_user_ids:
                await notification_svc.create_notification(
                    payload=NotificationCreate(
                        user_id=user_id,
                        title="Fleet Maintenance Due",
                        body=body,
                        notification_type="fleet_alert",
                    )
                )
            await notification_svc._send_push_to_users(
                staff_user_ids,
                "Fleet Maintenance Due",
                body,
                f"/fleet/{vehicle.id}",
            )
        await session.commit()


async def check_vehicle_insurance_expiry(ctx: dict[str, object]) -> None:
    """Alert staff when vehicle insurance expires within 30 days or is overdue."""
    cutoff = date.today() + timedelta(days=30)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Vehicle).where(
                and_(
                    Vehicle.deleted_at.is_(None),
                    Vehicle.insurance_expiry_date.isnot(None),
                    Vehicle.insurance_expiry_date <= cutoff,
                )
            )
        )
        expiring_vehicles = result.scalars().all()

        if not expiring_vehicles:
            return

        staff_user_ids = await _staff_user_ids(session, pc.VEHICLE_READ)
        if not staff_user_ids:
            return

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for vehicle in expiring_vehicles:
            for user_id in staff_user_ids:
                await notification_svc.create_notification(
                    payload=NotificationCreate(
                        user_id=user_id,
                        title="Vehicle Insurance Expiry Warning",
                        body=(
                            f"Insurance for vehicle '{vehicle.license_plate}' "
                            f"expires on {vehicle.insurance_expiry_date}."
                        ),
                        notification_type="expiry_alert",
                    )
                )
        # Push notifications for insurance expiry
        for vehicle in expiring_vehicles:
            await notification_svc._send_push_to_users(
                staff_user_ids,
                "Vehicle Insurance Expiring",
                f"Insurance for '{vehicle.license_plate}' expires on {vehicle.insurance_expiry_date}.",
                "/fleet",
            )
        await session.commit()


async def check_equipment_checkout_expiry(ctx: dict[str, object]) -> None:
    """Alert staff when checked-out equipment is past its expected return date."""
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EquipmentCheckout).where(
                and_(
                    EquipmentCheckout.returned_at.is_(None),
                    EquipmentCheckout.expected_return_at.isnot(None),
                    EquipmentCheckout.expected_return_at <= now,
                )
            )
        )
        overdue_checkouts = result.scalars().all()

        if not overdue_checkouts:
            return

        staff_user_ids = await _staff_user_ids(session, pc.VEHICLE_READ)
        if not staff_user_ids:
            return

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for checkout in overdue_checkouts:
            for user_id in staff_user_ids:
                due_date = (
                    checkout.expected_return_at.isoformat()
                    if checkout.expected_return_at
                    else "unknown"
                )
                await notification_svc.create_notification(
                    payload=NotificationCreate(
                        user_id=user_id,
                        title="Equipment Return Overdue",
                        body=(
                            f"Equipment '{checkout.equipment_name}' was due back on "
                            f"{due_date} and is still checked out."
                        ),
                        notification_type="fleet_alert",
                    )
                )
        # Push notifications for overdue equipment
        for checkout in overdue_checkouts:
            due_date = (
                checkout.expected_return_at.isoformat()
                if checkout.expected_return_at
                else "unknown"
            )
            await notification_svc._send_push_to_users(
                staff_user_ids,
                "Equipment Overdue",
                f"Equipment '{checkout.equipment_name}' was due back on {due_date}.",
                "/fleet",
            )
        await session.commit()
