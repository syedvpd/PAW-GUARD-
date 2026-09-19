"""FleetService: owns vehicle fleet business behaviour (RULE-003)."""

import uuid
from datetime import UTC, date, datetime, timedelta

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType, User
from pawguard.modules.fleet.models import (
    BreakdownStatus,
    EquipmentAsset,
    EquipmentCheckout,
    EquipmentCondition,
    FleetBreakdownReport,
    FleetMaintenance,
    FuelLog,
    Vehicle,
    VehicleStatus,
    VehicleType,
)
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.schemas import (
    BreakdownReportCreate,
    BreakdownReportResponse,
    BreakdownReportUpdate,
    EquipmentAssetCreate,
    EquipmentAssetResponse,
    EquipmentAssetUpdate,
    EquipmentCheckoutCreate,
    EquipmentCheckoutResponse,
    EquipmentReturnRequest,
    FleetSummaryResponse,
    FleetSummaryVehicle,
    FuelLogCreate,
    FuelLogResponse,
    MaintenanceCreate,
    MaintenanceResponse,
    VehicleCreate,
    VehicleResponse,
    VehicleUpdate,
)
from pawguard.services.audit_service import AuditService

DEFAULT_CHECKOUT_DURATION = timedelta(days=14)
MAINTENANCE_DUE_WINDOW = timedelta(days=14)
INSURANCE_EXPIRY_WINDOW = timedelta(days=30)

VALID_FLEET_TRANSITIONS: dict[str, set[str]] = {
    "active": {"in_maintenance", "out_of_service"},
    "in_maintenance": {"active", "out_of_service"},
    "out_of_service": {"in_maintenance"},
}


class FleetService:
    def __init__(
        self,
        repository: FleetRepository,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service

    async def create_vehicle(
        self,
        payload: VehicleCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Vehicle:
        if await self._repo.get_vehicle_by_plate(payload.license_plate) is not None:
            raise ConflictError(f"Vehicle with plate '{payload.license_plate}' already exists.")
        if payload.primary_driver_id is not None:
            driver_user = await self._repo._session.get(User, payload.primary_driver_id)
            if driver_user is None or driver_user.deleted_at is not None:
                raise NotFoundError(
                    f"Primary driver user with ID '{payload.primary_driver_id}' not found."
                )
            if not getattr(driver_user, "can_drive", False):
                raise ValidationFailedError(
                    f"User '{driver_user.full_name}' is not authorized to drive (can_drive=False)."
                )
        vehicle = await self._repo.create_vehicle(Vehicle(**payload.model_dump()))
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"vehicle_id": str(vehicle.id), "license_plate": vehicle.license_plate},
            )
        return vehicle

    async def update_vehicle(
        self,
        vehicle_id: uuid.UUID,
        payload: VehicleUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Vehicle:
        vehicle = await self._repo.get_vehicle(vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found.")
        if payload.license_plate and payload.license_plate != vehicle.license_plate:
            existing = await self._repo.get_vehicle_by_plate(payload.license_plate)
            if existing is not None:
                raise ConflictError(f"Vehicle with plate '{payload.license_plate}' already exists.")
        if payload.primary_driver_id is not None:
            driver_user = await self._repo._session.get(User, payload.primary_driver_id)
            if driver_user is None or driver_user.deleted_at is not None:
                raise NotFoundError(
                    f"Primary driver user with ID '{payload.primary_driver_id}' not found."
                )
            if not getattr(driver_user, "can_drive", False):
                raise ValidationFailedError(
                    f"User '{driver_user.full_name}' is not authorized to drive (can_drive=False)."
                )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(vehicle, field, value)
        await self._repo._session.flush()
        await self._repo._session.refresh(vehicle, attribute_names=["updated_at"])
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"vehicle_id": str(vehicle_id)},
            )
        return vehicle

    async def update_vehicle_status(
        self,
        vehicle_id: uuid.UUID,
        status: VehicleStatus,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Vehicle:
        vehicle = await self._repo.get_vehicle(vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found.")

        current_val = (
            vehicle.status.value if hasattr(vehicle.status, "value") else str(vehicle.status)
        )
        target_val = status.value if hasattr(status, "value") else str(status)
        if current_val != target_val:
            allowed = VALID_FLEET_TRANSITIONS.get(current_val, set())
            if target_val not in allowed:
                raise ValidationFailedError(
                    f"Cannot transition vehicle from '{current_val}' to '{target_val}'."
                )

        updated = await self._repo.update_vehicle_status(vehicle_id, status)
        if updated is None:
            raise NotFoundError("Failed to update vehicle status.")
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"vehicle_id": str(vehicle_id), "new_status": status.value},
            )
        return updated

    async def get_vehicle(self, vehicle_id: uuid.UUID) -> Vehicle:
        vehicle = await self._repo.get_vehicle(vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found.")
        return vehicle

    async def soft_delete_vehicle(
        self,
        vehicle_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        vehicle = await self._repo.get_vehicle(vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found.")
        await self._repo.soft_delete_vehicle(vehicle_id)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"vehicle_id": str(vehicle_id)},
            )

    async def list_vehicles_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: VehicleStatus | None = None,
        vehicle_type: VehicleType | None = None,
    ) -> PaginatedResponse[VehicleResponse]:
        results, total = await self._repo.paginate_vehicles(
            page=page,
            sort=sort,
            search_term=search_term,
            status=status,
            vehicle_type=vehicle_type,
        )
        return PaginatedResponse(
            data=[VehicleResponse.model_validate(v) for v in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def log_maintenance(
        self,
        payload: MaintenanceCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FleetMaintenance:
        vehicle = await self._repo.get_vehicle(payload.vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found.")
        record = await self._repo.create_maintenance(FleetMaintenance(**payload.model_dump()))
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"maintenance_id": str(record.id), "vehicle_id": str(payload.vehicle_id)},
            )
        return record

    async def list_maintenance_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        vehicle_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[MaintenanceResponse]:
        results, total = await self._repo.paginate_maintenance(
            page=page,
            sort=sort,
            vehicle_id=vehicle_id,
        )
        return PaginatedResponse(
            data=[MaintenanceResponse.model_validate(r) for r in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def bulk_update_status(
        self,
        ids: list[uuid.UUID],
        status: VehicleStatus,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        if not ids:
            return 0
        vehicles = await self._repo.list_vehicles_by_ids(ids)
        if not vehicles:
            raise NotFoundError("No vehicles found for the provided IDs.")

        # State machine transition rules enforced for every vehicle
        target_val = status.value if hasattr(status, "value") else str(status)
        for v in vehicles:
            curr_val = v.status.value if hasattr(v.status, "value") else str(v.status)
            if curr_val != target_val:
                allowed = VALID_FLEET_TRANSITIONS.get(curr_val, set())
                if target_val not in allowed:
                    raise ConflictError(
                        f"Cannot transition vehicle(s) {v.license_plate} directly from "
                        f"{curr_val} to {target_val} without passing through in_maintenance."
                    )

        count = await self._repo.bulk_update_vehicle_status(ids, status)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "vehicle_ids": [str(i) for i in ids],
                    "new_status": status.value,
                    "count": count,
                },
            )
        return count

    async def bulk_soft_delete(
        self,
        ids: list[uuid.UUID],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_soft_delete_vehicles(ids)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"vehicle_ids": [str(i) for i in ids], "count": count},
            )
        return count

    async def checkout_equipment(
        self,
        payload: EquipmentCheckoutCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> EquipmentCheckout:
        if payload.assigned_to_vehicle_id is not None:
            vehicle = await self._repo.get_vehicle(payload.assigned_to_vehicle_id)
            if vehicle is None:
                raise NotFoundError("Vehicle not found.")
        equipment_name = payload.equipment_name.strip()
        if payload.asset_id is not None:
            asset = await self._repo.get_asset(payload.asset_id)
            if asset is None:
                raise NotFoundError("Equipment asset not found.")
            if asset.condition == EquipmentCondition.RETIRED:
                raise ConflictError(f"'{asset.name}' is retired and cannot be checked out.")
            if await self._repo.get_outstanding_checkout_for_asset(asset.id) is not None:
                raise ConflictError(f"'{asset.name}' is already checked out.")
            equipment_name = equipment_name or asset.name
        if not equipment_name:
            raise ValidationFailedError("equipment_name or asset_id is required.")
        checked_out_at = datetime.now(UTC)
        expected_return_at = self._resolve_expected_return_at(payload.expected_return_at)
        record = await self._repo.create_equipment_checkout(
            EquipmentCheckout(
                **payload.model_dump(exclude={"expected_return_at", "equipment_name"}),
                equipment_name=equipment_name,
                checked_out_at=checked_out_at,
                expected_return_at=expected_return_at,
            )
        )
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_EQUIPMENT_CHECKED_OUT,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "checkout_id": str(record.id),
                    "equipment_name": record.equipment_name,
                    "expected_return_at": record.expected_return_at.isoformat()
                    if record.expected_return_at
                    else None,
                },
            )
        return record

    @staticmethod
    def _resolve_expected_return_at(value: datetime | None) -> datetime:
        """Return the enforced due date for a checkout.

        Either an explicit future timestamp is honoured, or a default
        ``DEFAULT_CHECKOUT_DURATION`` window is applied from checkout time.
        A past timestamp is rejected (PRR 3.13 expiry enforcement).
        """
        now = datetime.now(UTC)
        if value is not None:
            value_utc = value if value.tzinfo else value.replace(tzinfo=UTC)
            if value_utc <= now:
                raise ConflictError("expected_return_at must be in the future for a new checkout.")
            return value_utc
        return now + DEFAULT_CHECKOUT_DURATION

    async def checkout_equipment_for_dispatch(
        self,
        *,
        rescue_dispatch_id: uuid.UUID,
        equipment_names: list[str],
        assigned_to_agent_id: uuid.UUID | None = None,
        assigned_to_vehicle_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> list[EquipmentCheckout]:
        """Auto-checkout equipment recorded on a rescue dispatch (PRR 3.3).

        The rescue module orchestrates the dispatch and delegates the fleet
        records here so equipment business rules stay in the fleet domain.
        The shared session keeps the checkouts atomic with the dispatch.
        """
        names = [name.strip() for name in equipment_names if name and name.strip()]
        if not names:
            return []
        if assigned_to_vehicle_id is not None:
            vehicle = await self._repo.get_vehicle(assigned_to_vehicle_id)
            if vehicle is None:
                raise NotFoundError("Vehicle not found.")
        checked_out_at = datetime.now(UTC)
        records = []
        for name in names:
            record = await self._repo.create_equipment_checkout(
                EquipmentCheckout(
                    equipment_name=name,
                    assigned_to_agent_id=assigned_to_agent_id,
                    assigned_to_vehicle_id=assigned_to_vehicle_id,
                    rescue_dispatch_id=rescue_dispatch_id,
                    checked_out_at=checked_out_at,
                    expected_return_at=checked_out_at + DEFAULT_CHECKOUT_DURATION,
                )
            )
            records.append(record)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_EQUIPMENT_CHECKED_OUT,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_dispatch_id": str(rescue_dispatch_id),
                    "equipment_count": len(records),
                    "equipment_names": names,
                },
            )
        return records

    async def release_equipment_for_dispatch(
        self,
        *,
        rescue_dispatch_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        """Mark every outstanding equipment checkout for a dispatch as returned."""
        released = await self._repo.release_equipment_for_dispatch(rescue_dispatch_id)
        if released and self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_EQUIPMENT_RETURNED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_dispatch_id": str(rescue_dispatch_id),
                    "returned_count": released,
                },
            )
        return released

    async def return_equipment(
        self,
        checkout_id: uuid.UUID,
        payload: EquipmentReturnRequest,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> EquipmentCheckout:
        record = await self._repo.get_equipment_checkout(checkout_id)
        if record is None:
            raise NotFoundError("Equipment checkout record not found.")
        if record.returned_at is not None:
            raise ConflictError("Equipment has already been returned.")
        record.returned_at = datetime.now(UTC)
        if payload.notes:
            record.notes = payload.notes
        if payload.condition is not None and record.asset_id is not None:
            asset = await self._repo.get_asset(record.asset_id)
            if asset is not None:
                asset.condition = payload.condition
        # Late return (PRR 3.13): never reject, but flag it on the ledger so
        # staff can follow up. The dispatch auto-release path skips this note
        # because dispatch equipment has no manual returner.
        if (
            record.rescue_dispatch_id is None
            and record.expected_return_at is not None
            and record.returned_at > record.expected_return_at
        ):
            late_note = (
                f"Returned late - expected {record.expected_return_at.isoformat()}, "
                f"returned {record.returned_at.isoformat()}."
            )
            record.notes = f"{record.notes}\n{late_note}" if record.notes else late_note
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_EQUIPMENT_RETURNED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"checkout_id": str(checkout_id)},
            )
        return record

    async def get_equipment_checkout(self, checkout_id: uuid.UUID) -> EquipmentCheckout:
        record = await self._repo.get_equipment_checkout(checkout_id)
        if record is None:
            raise NotFoundError("Equipment checkout record not found.")
        return record

    async def list_equipment_checkouts_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        outstanding_only: bool = False,
    ) -> PaginatedResponse[EquipmentCheckoutResponse]:
        results, total = await self._repo.paginate_equipment_checkouts(
            page=page,
            sort=sort,
            search_term=search_term,
            outstanding_only=outstanding_only,
        )
        return PaginatedResponse(
            data=[EquipmentCheckoutResponse.model_validate(r) for r in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def log_fuel(
        self,
        vehicle_id: uuid.UUID,
        payload: FuelLogCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FuelLog:
        vehicle = await self._repo.get_vehicle(vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found.")
        log = FuelLog(
            vehicle_id=vehicle_id,
            filled_by_id=actor_id,
            **payload.model_dump(),
            filled_at=datetime.now(UTC),
        )
        if payload.mileage_at_fill > vehicle.mileage:
            vehicle.mileage = payload.mileage_at_fill
        record = await self._repo.create_fuel_log(log)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"fuel_log_id": str(record.id), "vehicle_id": str(vehicle_id)},
            )
        return record

    async def get_fuel_logs_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        vehicle_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[FuelLogResponse]:
        results, total = await self._repo.paginate_fuel_logs(
            page=page,
            sort=sort,
            vehicle_id=vehicle_id,
        )
        return PaginatedResponse(
            data=[FuelLogResponse.model_validate(r) for r in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def get_fuel_log(self, log_id: uuid.UUID) -> FuelLog:
        log = await self._repo.get_fuel_log(log_id)
        if log is None:
            raise NotFoundError("Fuel log not found.")
        return log

    async def create_breakdown_report(
        self,
        payload: BreakdownReportCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FleetBreakdownReport:
        vehicle = await self._repo.get_vehicle(payload.vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found.")

        driver_id = payload.driver_id or actor_id
        if driver_id is not None and not await self._repo.user_exists(driver_id):
            raise ValidationFailedError(f"Driver user {driver_id} does not exist.")

        report = FleetBreakdownReport(
            vehicle_id=payload.vehicle_id,
            driver_id=driver_id,
            breakdown_type=payload.breakdown_type,
            severity=payload.severity,
            description=payload.description,
            location=payload.location,
            reported_at=datetime.now(UTC),
            status=BreakdownStatus.REPORTED,
            notes=payload.notes,
        )
        record = await self._repo.create_breakdown_report(report)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "breakdown_report_id": str(record.id),
                    "vehicle_id": str(payload.vehicle_id),
                },
            )
        return record

    async def get_breakdown_report(self, report_id: uuid.UUID) -> FleetBreakdownReport:
        report = await self._repo.get_breakdown_report(report_id)
        if report is None:
            raise NotFoundError("Breakdown report not found.")
        return report

    async def update_breakdown_report(
        self,
        report_id: uuid.UUID,
        payload: BreakdownReportUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FleetBreakdownReport:
        report = await self._repo.get_breakdown_report(report_id)
        if report is None:
            raise NotFoundError("Breakdown report not found.")

        if payload.breakdown_type is not None:
            report.breakdown_type = payload.breakdown_type
        if payload.severity is not None:
            report.severity = payload.severity
        if payload.description is not None:
            report.description = payload.description
        if payload.location is not None:
            report.location = payload.location
        if payload.status is not None:
            report.status = payload.status
        if payload.resolved_at is not None:
            report.resolved_at = payload.resolved_at
        elif payload.status == "resolved" and report.resolved_at is None:
            report.resolved_at = datetime.now(UTC)
        if payload.notes is not None:
            report.notes = payload.notes

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FLEET_VEHICLE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"breakdown_report_id": str(report.id), "status": report.status},
            )
        return report

    async def list_breakdown_reports_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        vehicle_id: uuid.UUID | None = None,
        status: str | None = None,
        search_term: str | None = None,
    ) -> PaginatedResponse[BreakdownReportResponse]:
        results, total = await self._repo.paginate_breakdown_reports(
            page=page,
            sort=sort,
            vehicle_id=vehicle_id,
            status=status,
            search_term=search_term,
        )
        return PaginatedResponse(
            data=[BreakdownReportResponse.model_validate(r) for r in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def create_asset(self, payload: EquipmentAssetCreate) -> EquipmentAssetResponse:
        if payload.serial_number and await self._repo.get_asset_by_serial(payload.serial_number):
            raise ConflictError(f"Serial number '{payload.serial_number}' is already registered.")
        asset = await self._repo.create_asset(EquipmentAsset(**payload.model_dump()))
        await self._repo._session.refresh(asset)
        return EquipmentAssetResponse.model_validate(asset)

    async def get_asset(self, asset_id: uuid.UUID) -> EquipmentAssetResponse:
        asset = await self._repo.get_asset(asset_id)
        if asset is None:
            raise NotFoundError("Equipment asset not found.")
        checkout = await self._repo.get_outstanding_checkout_for_asset(asset_id)
        response = EquipmentAssetResponse.model_validate(asset)
        response.current_checkout_id = checkout.id if checkout else None
        return response

    async def update_asset(
        self, asset_id: uuid.UUID, payload: EquipmentAssetUpdate
    ) -> EquipmentAssetResponse:
        asset = await self._repo.get_asset(asset_id)
        if asset is None:
            raise NotFoundError("Equipment asset not found.")
        if payload.serial_number and payload.serial_number != asset.serial_number:
            if await self._repo.get_asset_by_serial(payload.serial_number):
                raise ConflictError(
                    f"Serial number '{payload.serial_number}' is already registered."
                )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(asset, field, value)
        await self._repo._session.flush()
        await self._repo._session.refresh(asset)
        return await self.get_asset(asset_id)

    async def list_assets_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        category: str | None = None,
        condition: str | None = None,
    ) -> PaginatedResponse[EquipmentAssetResponse]:
        rows, total = await self._repo.paginate_assets(
            page=page, sort=sort, search_term=search_term, category=category, condition=condition
        )
        data = []
        for asset, checkout_id in rows:
            item = EquipmentAssetResponse.model_validate(asset)
            item.current_checkout_id = checkout_id
            data.append(item)
        return PaginatedResponse(data=data, meta=build_pagination_meta(total=total, params=page))

    async def get_summary(self) -> FleetSummaryResponse:
        today = date.today()
        by_status = await self._repo.count_vehicles_by_status()
        insurance = await self._repo.list_insurance_expiring(today + INSURANCE_EXPIRY_WINDOW)
        maintenance = await self._repo.list_maintenance_due(today + MAINTENANCE_DUE_WINDOW)
        outstanding, overdue = await self._repo.count_equipment(datetime.now(UTC))
        return FleetSummaryResponse(
            total_vehicles=sum(by_status.values()),
            by_status=by_status,
            insurance_expiring=[
                FleetSummaryVehicle(
                    id=v.id,
                    license_plate=v.license_plate,
                    make_model=v.make_model,
                    due_date=v.insurance_expiry_date,
                )
                for v in insurance
                if v.insurance_expiry_date is not None
            ],
            maintenance_due=[
                FleetSummaryVehicle(
                    id=v.id,
                    license_plate=v.license_plate,
                    make_model=v.make_model,
                    due_date=m.next_due_date,
                )
                for v, m in maintenance
                if m.next_due_date is not None
            ],
            outstanding_equipment=outstanding,
            overdue_equipment=overdue,
            open_breakdowns=await self._repo.count_open_breakdowns(),
        )
