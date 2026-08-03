"""Data access for fleet management."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.fleet.models import (
    EquipmentCheckout,
    FleetMaintenance,
    FuelLog,
    Vehicle,
    VehicleStatus,
    VehicleType,
)


class FleetRepository:
    VEHICLE_SEARCH_FIELDS = ("make_model", "license_plate")
    VEHICLE_SORTABLE_FIELDS = {
        "make_model", "license_plate", "status", "vehicle_type", "mileage",
        "created_at", "updated_at",
    }
    MAINTENANCE_SORTABLE_FIELDS = {
        "service_date", "cost", "created_at",
    }
    EQUIPMENT_SEARCH_FIELDS = ("equipment_name", "notes")
    EQUIPMENT_SORTABLE_FIELDS = {
        "equipment_name", "checked_out_at", "expected_return_at", "returned_at", "created_at",
    }
    FUEL_SORTABLE_FIELDS = {"filled_at", "volume_litres", "cost", "mileage_at_fill"}
    FUEL_SEARCH_FIELDS = ("vendor", "notes")

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_vehicle(self, vehicle: Vehicle) -> Vehicle:
        self._session.add(vehicle)
        await self._session.flush()
        return vehicle

    async def get_vehicle(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        stmt = select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_vehicle_by_plate(self, license_plate: str) -> Vehicle | None:
        stmt = (
            select(Vehicle)
            .where(Vehicle.license_plate == license_plate, Vehicle.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def paginate_vehicles(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: VehicleStatus | None = None,
        vehicle_type: VehicleType | None = None,
    ) -> tuple[Sequence[Vehicle], int]:
        stmt = select(Vehicle).where(Vehicle.deleted_at.is_(None))

        search_filter = build_search_filter(Vehicle, search_term, self.VEHICLE_SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if status is not None:
            stmt = stmt.where(Vehicle.status == status)

        if vehicle_type is not None:
            stmt = stmt.where(Vehicle.vehicle_type == vehicle_type)

        stmt = apply_sorting(stmt, sort, self.VEHICLE_SORTABLE_FIELDS)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def paginate_maintenance(
        self,
        page: PageParams,
        sort: SortParams,
        vehicle_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[FleetMaintenance], int]:
        stmt = select(FleetMaintenance)

        if vehicle_id is not None:
            stmt = stmt.where(FleetMaintenance.vehicle_id == vehicle_id)

        stmt = apply_sorting(
            stmt, sort, self.MAINTENANCE_SORTABLE_FIELDS, default_field="service_date"
        )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def soft_delete_vehicle(self, vehicle_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime
        stmt = (
            update(Vehicle)
            .where(Vehicle.id == vehicle_id, Vehicle.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]

    async def update_vehicle_status(
        self, vehicle_id: uuid.UUID, status: VehicleStatus,
    ) -> Vehicle | None:
        stmt = (
            update(Vehicle)
            .where(Vehicle.id == vehicle_id, Vehicle.deleted_at.is_(None))
            .values(status=status)
            .returning(Vehicle)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_maintenance(self, record: FleetMaintenance) -> FleetMaintenance:
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_vehicles_by_ids(self, ids: list[uuid.UUID]) -> Sequence[Vehicle]:
        stmt = select(Vehicle).where(Vehicle.id.in_(ids), Vehicle.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalars().all()

    async def bulk_update_vehicle_status(self, ids: list[uuid.UUID], status: VehicleStatus) -> int:
        stmt = (
            update(Vehicle)
            .where(Vehicle.id.in_(ids), Vehicle.deleted_at.is_(None))
            .values(status=status)
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def bulk_soft_delete_vehicles(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime
        stmt = (
            update(Vehicle)
            .where(Vehicle.id.in_(ids), Vehicle.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def create_equipment_checkout(self, record: EquipmentCheckout) -> EquipmentCheckout:
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_checkouts_for_dispatch(
        self, rescue_dispatch_id: uuid.UUID
    ) -> Sequence[EquipmentCheckout]:
        stmt = (
            select(EquipmentCheckout)
            .where(
                EquipmentCheckout.rescue_dispatch_id == rescue_dispatch_id,
                EquipmentCheckout.returned_at.is_(None),
            )
            .order_by(EquipmentCheckout.checked_out_at)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def release_equipment_for_dispatch(self, rescue_dispatch_id: uuid.UUID) -> int:
        from datetime import UTC, datetime

        stmt = (
            update(EquipmentCheckout)
            .where(
                EquipmentCheckout.rescue_dispatch_id == rescue_dispatch_id,
                EquipmentCheckout.returned_at.is_(None),
            )
            .values(returned_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def get_equipment_checkout(self, checkout_id: uuid.UUID) -> EquipmentCheckout | None:
        stmt = select(EquipmentCheckout).where(EquipmentCheckout.id == checkout_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def paginate_equipment_checkouts(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        outstanding_only: bool = False,
    ) -> tuple[Sequence[EquipmentCheckout], int]:
        stmt = select(EquipmentCheckout)

        search_filter = build_search_filter(
            EquipmentCheckout, search_term, self.EQUIPMENT_SEARCH_FIELDS
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if outstanding_only:
            stmt = stmt.where(EquipmentCheckout.returned_at.is_(None))

        stmt = apply_sorting(stmt, sort, self.EQUIPMENT_SORTABLE_FIELDS)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()
        return results, total

    async def create_fuel_log(self, log: FuelLog) -> FuelLog:
        self._session.add(log)
        await self._session.flush()
        return log

    async def get_fuel_log(self, log_id: uuid.UUID) -> FuelLog | None:
        stmt = select(FuelLog).where(FuelLog.id == log_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def paginate_fuel_logs(
        self,
        page: PageParams,
        sort: SortParams,
        vehicle_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[FuelLog], int]:
        stmt = select(FuelLog)

        if vehicle_id is not None:
            stmt = stmt.where(FuelLog.vehicle_id == vehicle_id)

        stmt = apply_sorting(stmt, sort, self.FUEL_SORTABLE_FIELDS, default_field="filled_at")

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()
        return results, total
