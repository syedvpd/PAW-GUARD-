"""FleetService: owns vehicle fleet business behaviour (RULE-003)."""

import uuid
from datetime import UTC, datetime

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.fleet.models import (
    EquipmentCheckout,
    FleetMaintenance,
    Vehicle,
    VehicleStatus,
)
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.schemas import (
    EquipmentCheckoutCreate,
    EquipmentCheckoutResponse,
    EquipmentReturnRequest,
    MaintenanceCreate,
    MaintenanceResponse,
    VehicleCreate,
    VehicleResponse,
    VehicleUpdate,
)
from pawguard.services.audit_service import AuditService


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
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(vehicle, field, value)
        await self._repo._session.flush()
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
    ) -> PaginatedResponse[VehicleResponse]:
        results, total = await self._repo.paginate_vehicles(
            page=page,
            sort=sort,
            search_term=search_term,
            status=status,
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
        record = await self._repo.create_equipment_checkout(
            EquipmentCheckout(
                **payload.model_dump(),
                checked_out_at=datetime.now(UTC),
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
                },
            )
        return record

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
