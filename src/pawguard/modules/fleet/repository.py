"""Data access for fleet management."""

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import bulk_set_column
from pawguard.core.pagination import PageParams
from pawguard.core.search import (
    SortParams,
    apply_equality_filters,
    apply_sorting,
    build_search_filter,
)
from pawguard.modules.auth.models import User
from pawguard.modules.fleet.models import (
    BreakdownStatus,
    EquipmentAsset,
    EquipmentCheckout,
    FleetBreakdownReport,
    FleetMaintenance,
    FuelLog,
    Vehicle,
    VehicleStatus,
    VehicleType,
)


class FleetRepository:
    VEHICLE_SEARCH_FIELDS = ("make_model", "license_plate")
    VEHICLE_SORTABLE_FIELDS = {
        "make_model",
        "license_plate",
        "status",
        "vehicle_type",
        "mileage",
        "created_at",
        "updated_at",
    }
    MAINTENANCE_SORTABLE_FIELDS = {
        "service_date",
        "cost",
        "created_at",
    }
    EQUIPMENT_SEARCH_FIELDS = ("equipment_name", "notes")
    EQUIPMENT_SORTABLE_FIELDS = {
        "equipment_name",
        "checked_out_at",
        "expected_return_at",
        "returned_at",
        "created_at",
    }
    FUEL_SORTABLE_FIELDS = {"filled_at", "volume_litres", "cost", "mileage_at_fill"}
    FUEL_SEARCH_FIELDS = ("vendor", "notes")
    BREAKDOWN_SORTABLE_FIELDS = {"reported_at", "severity", "status", "created_at"}
    BREAKDOWN_SEARCH_FIELDS = ("breakdown_type", "description", "location", "notes")
    ASSET_SEARCH_FIELDS = ("name", "serial_number", "notes")
    ASSET_SORTABLE_FIELDS = {"name", "category", "condition", "created_at"}

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all_vehicles(self) -> Sequence[Vehicle]:
        """Return all non-deleted vehicles (for availability queries)."""
        stmt = select(Vehicle).where(Vehicle.deleted_at.is_(None)).order_by(Vehicle.license_plate)
        return (await self._session.execute(stmt)).scalars().all()

    async def create_vehicle(self, vehicle: Vehicle) -> Vehicle:
        self._session.add(vehicle)
        await self._session.flush()
        return vehicle

    async def get_vehicle(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        stmt = select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_vehicle_for_update(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        stmt = select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.deleted_at.is_(None))
        if self._session.bind and self._session.bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_vehicle_by_plate(self, license_plate: str) -> Vehicle | None:
        stmt = select(Vehicle).where(
            Vehicle.license_plate == license_plate, Vehicle.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def user_exists(self, user_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one() > 0

    async def paginate_vehicles(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: VehicleStatus | None = None,
        vehicle_type: VehicleType | None = None,
    ) -> tuple[Sequence[Vehicle], int]:
        total_count = func.count().over().label("_total_count")
        stmt = select(Vehicle, total_count).where(Vehicle.deleted_at.is_(None))

        search_filter = build_search_filter(Vehicle, search_term, self.VEHICLE_SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        stmt = apply_equality_filters(stmt, Vehicle, status=status, vehicle_type=vehicle_type)
        stmt = apply_sorting(stmt, sort, self.VEHICLE_SORTABLE_FIELDS)

        stmt = stmt.offset(page.offset).limit(page.limit)
        rows = (await self._session.execute(stmt)).all()

        results = [row[0] for row in rows]
        total = int(rows[0]._total_count) if rows else 0

        return results, total

    async def paginate_maintenance(
        self,
        page: PageParams,
        sort: SortParams,
        vehicle_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[FleetMaintenance], int]:
        total_count = func.count().over().label("_total_count")
        stmt = select(FleetMaintenance, total_count)
        stmt = apply_equality_filters(stmt, FleetMaintenance, vehicle_id=vehicle_id)

        stmt = apply_sorting(
            stmt, sort, self.MAINTENANCE_SORTABLE_FIELDS, default_field="service_date"
        )

        stmt = stmt.offset(page.offset).limit(page.limit)
        rows = (await self._session.execute(stmt)).all()

        results = [row[0] for row in rows]
        total = int(rows[0]._total_count) if rows else 0

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
        self,
        vehicle_id: uuid.UUID,
        status: VehicleStatus,
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
        return await bulk_set_column(self._session, Vehicle, ids, status=status)

    async def bulk_soft_delete_vehicles(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        return await bulk_set_column(self._session, Vehicle, ids, deleted_at=datetime.now(UTC))

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
        total_count = func.count().over().label("_total_count")
        stmt = select(EquipmentCheckout, total_count)

        search_filter = build_search_filter(
            EquipmentCheckout, search_term, self.EQUIPMENT_SEARCH_FIELDS
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if outstanding_only:
            stmt = stmt.where(EquipmentCheckout.returned_at.is_(None))

        stmt = apply_sorting(stmt, sort, self.EQUIPMENT_SORTABLE_FIELDS)

        stmt = stmt.offset(page.offset).limit(page.limit)
        rows = (await self._session.execute(stmt)).all()

        results = [row[0] for row in rows]
        total = int(rows[0]._total_count) if rows else 0

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
        total_count = func.count().over().label("_total_count")
        stmt = select(FuelLog, total_count)
        stmt = apply_equality_filters(stmt, FuelLog, vehicle_id=vehicle_id)

        stmt = apply_sorting(stmt, sort, self.FUEL_SORTABLE_FIELDS, default_field="filled_at")

        stmt = stmt.offset(page.offset).limit(page.limit)
        rows = (await self._session.execute(stmt)).all()

        results = [row[0] for row in rows]
        total = int(rows[0]._total_count) if rows else 0

        return results, total

    async def create_breakdown_report(self, report: FleetBreakdownReport) -> FleetBreakdownReport:
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_breakdown_report(self, report_id: uuid.UUID) -> FleetBreakdownReport | None:
        stmt = select(FleetBreakdownReport).where(FleetBreakdownReport.id == report_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def paginate_breakdown_reports(
        self,
        page: PageParams,
        sort: SortParams,
        vehicle_id: uuid.UUID | None = None,
        status: str | None = None,
        search_term: str | None = None,
    ) -> tuple[Sequence[FleetBreakdownReport], int]:
        total_count = func.count().over().label("_total_count")
        stmt = select(FleetBreakdownReport, total_count)

        stmt = apply_equality_filters(
            stmt, FleetBreakdownReport, vehicle_id=vehicle_id, status=status
        )

        search_filter = build_search_filter(
            FleetBreakdownReport, search_term, self.BREAKDOWN_SEARCH_FIELDS
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        stmt = apply_sorting(
            stmt, sort, self.BREAKDOWN_SORTABLE_FIELDS, default_field="reported_at"
        )

        stmt = stmt.offset(page.offset).limit(page.limit)
        rows = (await self._session.execute(stmt)).all()

        results = [row[0] for row in rows]
        total = int(rows[0]._total_count) if rows else 0

        return results, total

    async def create_asset(self, asset: EquipmentAsset) -> EquipmentAsset:
        self._session.add(asset)
        await self._session.flush()
        return asset

    async def get_asset(self, asset_id: uuid.UUID) -> EquipmentAsset | None:
        return await self._session.get(EquipmentAsset, asset_id)

    async def get_asset_by_serial(self, serial_number: str) -> EquipmentAsset | None:
        stmt = select(EquipmentAsset).where(EquipmentAsset.serial_number == serial_number)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_outstanding_checkout_for_asset(
        self, asset_id: uuid.UUID
    ) -> EquipmentCheckout | None:
        stmt = select(EquipmentCheckout).where(
            EquipmentCheckout.asset_id == asset_id, EquipmentCheckout.returned_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def paginate_assets(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        category: str | None = None,
        condition: str | None = None,
    ) -> tuple[Sequence[tuple[EquipmentAsset, uuid.UUID | None]], int]:
        total_count = func.count().over().label("_total_count")
        current_checkout = (
            select(EquipmentCheckout.id)
            .where(
                EquipmentCheckout.asset_id == EquipmentAsset.id,
                EquipmentCheckout.returned_at.is_(None),
            )
            .limit(1)
            .correlate(EquipmentAsset)
            .scalar_subquery()
            .label("current_checkout_id")
        )
        stmt = select(EquipmentAsset, current_checkout, total_count)
        search_filter = build_search_filter(EquipmentAsset, search_term, self.ASSET_SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        stmt = apply_equality_filters(stmt, EquipmentAsset, category=category, condition=condition)
        stmt = apply_sorting(stmt, sort, self.ASSET_SORTABLE_FIELDS, default_field="name")
        stmt = stmt.offset(page.offset).limit(page.limit)
        rows = (await self._session.execute(stmt)).all()
        total = int(rows[0]._total_count) if rows else 0
        return [(row[0], row[1]) for row in rows], total

    async def count_vehicles_by_status(self) -> dict[str, int]:
        stmt = (
            select(Vehicle.status, func.count())
            .where(Vehicle.deleted_at.is_(None))
            .group_by(Vehicle.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(getattr(status, "value", status)): int(count) for status, count in rows}

    async def list_insurance_expiring(self, cutoff: date) -> Sequence[Vehicle]:
        stmt = (
            select(Vehicle)
            .where(
                Vehicle.deleted_at.is_(None),
                Vehicle.insurance_expiry_date.isnot(None),
                Vehicle.insurance_expiry_date <= cutoff,
            )
            .order_by(Vehicle.insurance_expiry_date)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_maintenance_due(
        self, cutoff: date
    ) -> Sequence[tuple[Vehicle, FleetMaintenance]]:
        """Latest maintenance record per vehicle whose next_due_date is on or before cutoff.

        Older records are superseded by the most recent service, so their stale
        next_due_date never counts as due.
        """
        ranked = select(
            FleetMaintenance.id.label("maintenance_id"),
            func.row_number()
            .over(
                partition_by=FleetMaintenance.vehicle_id,
                order_by=(FleetMaintenance.service_date.desc(), FleetMaintenance.created_at.desc()),
            )
            .label("rn"),
        ).subquery()
        stmt = (
            select(Vehicle, FleetMaintenance)
            .join(FleetMaintenance, FleetMaintenance.vehicle_id == Vehicle.id)
            .join(ranked, ranked.c.maintenance_id == FleetMaintenance.id)
            .where(
                ranked.c.rn == 1,
                Vehicle.deleted_at.is_(None),
                FleetMaintenance.next_due_date.isnot(None),
                FleetMaintenance.next_due_date <= cutoff,
            )
            .order_by(FleetMaintenance.next_due_date)
        )
        return [(row[0], row[1]) for row in (await self._session.execute(stmt)).all()]

    async def count_equipment(self, now: datetime) -> tuple[int, int]:
        outstanding = EquipmentCheckout.returned_at.is_(None)
        stmt = select(
            func.count().filter(outstanding),
            func.count().filter(
                outstanding,
                EquipmentCheckout.expected_return_at.isnot(None),
                EquipmentCheckout.expected_return_at <= now,
            ),
        ).select_from(EquipmentCheckout)
        row = (await self._session.execute(stmt)).one()
        return int(row[0]), int(row[1])

    async def count_open_breakdowns(self) -> int:
        stmt = (
            select(func.count())
            .select_from(FleetBreakdownReport)
            .where(FleetBreakdownReport.status != BreakdownStatus.RESOLVED)
        )
        return int((await self._session.execute(stmt)).scalar_one())
