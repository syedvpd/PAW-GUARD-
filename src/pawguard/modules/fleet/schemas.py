"""Pydantic schemas for fleet management."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pawguard.modules.fleet.models import (
    BreakdownSeverity,
    BreakdownStatus,
    EquipmentCategory,
    EquipmentCondition,
    MaintenanceType,
    VehicleStatus,
    VehicleType,
)


class VehicleCreate(BaseModel):
    make_model: str = Field(
        "Rescue Vehicle", min_length=1, max_length=255, examples=["Ford Transit 2022"]
    )
    license_plate: str = Field(..., min_length=1, max_length=64, examples=["RESCUE-01"])
    vehicle_type: VehicleType = VehicleType.RESCUE_VAN
    status: VehicleStatus = VehicleStatus.ACTIVE
    mileage: int = Field(0, ge=0, examples=[12500])
    primary_driver_id: uuid.UUID | None = Field(
        None,
        description="Optional UUID of the primary driver (user.id). Omit or set to null if no driver assigned.",
        examples=[None],
    )
    insurance_provider: str | None = Field(None, max_length=255)
    insurance_policy_number: str | None = Field(None, max_length=128)
    insurance_expiry_date: date | None = None
    insurance_contact_phone: str | None = Field(None, max_length=32)

    @model_validator(mode="before")
    @classmethod
    def flex_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # License plate alias
        lp = (
            d.get("license_plate")
            or d.get("registration_number")
            or d.get("registration_no")
            or d.get("plate_number")
            or d.get("plate")
        )
        if lp:
            d["license_plate"] = str(lp).strip()
        else:
            import secrets

            d["license_plate"] = f"VEH-{secrets.token_hex(3).upper()}"

        # Make model alias
        mm = (
            d.get("make_model")
            or d.get("vehicle_model")
            or d.get("model")
            or d.get("vehicle_type")
            or d.get("name")
        )
        if mm:
            d["make_model"] = str(mm).strip()
        else:
            d["make_model"] = "Rescue Fleet Unit"

        # Primary driver alias
        drv = d.get("primary_driver_id") or d.get("driver_id") or d.get("agent_id")
        if drv and isinstance(drv, str) and drv.strip():
            try:
                d["primary_driver_id"] = str(uuid.UUID(drv.strip()))
            except ValueError:
                d["primary_driver_id"] = None
        elif not drv:
            d["primary_driver_id"] = None

        return d


class VehicleUpdate(BaseModel):
    make_model: str | None = Field(
        None, min_length=1, max_length=255, examples=["Ford Transit 2022"]
    )
    license_plate: str | None = Field(None, min_length=1, max_length=64, examples=["RESCUE-01"])
    vehicle_type: VehicleType | None = Field(None, examples=["ambulance"])
    status: VehicleStatus | None = Field(None, examples=["active"])
    mileage: int | None = Field(None, ge=0, examples=[12800])
    primary_driver_id: uuid.UUID | None = Field(
        None,
        description="Optional UUID of the primary driver (user.id). Omit or set to null if no driver assigned.",
        examples=[None],
    )
    insurance_provider: str | None = Field(
        None, max_length=255, examples=["SafeGuard Insurance Co."]
    )
    insurance_policy_number: str | None = Field(None, max_length=128, examples=["POL-2026-004521"])
    insurance_expiry_date: date | None = Field(None, examples=["2027-01-31"])
    insurance_contact_phone: str | None = Field(None, max_length=32, examples=["+1-555-0188"])


class VehicleStatusUpdate(BaseModel):
    status: VehicleStatus = Field(
        ..., description="New status for the vehicle", examples=["in_maintenance"]
    )


class VehicleResponse(BaseModel):
    id: uuid.UUID
    make_model: str
    license_plate: str
    vehicle_type: VehicleType | None = VehicleType.RESCUE_VAN
    status: VehicleStatus
    mileage: int
    primary_driver_id: uuid.UUID | None
    insurance_provider: str | None = None
    insurance_policy_number: str | None = None
    insurance_expiry_date: date | None = None
    insurance_contact_phone: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaintenanceCreate(BaseModel):
    vehicle_id: uuid.UUID
    service_date: date = Field(..., examples=["2026-07-15"])
    maintenance_type: MaintenanceType = MaintenanceType.SERVICE
    description: str = Field(..., min_length=1, examples=["Oil change and brake inspection"])
    cost: float = Field(0.0, ge=0.0, examples=[150.0])
    next_due_date: date | None = Field(None, examples=["2027-01-15"])


class MaintenanceResponse(BaseModel):
    id: uuid.UUID
    vehicle_id: uuid.UUID
    service_date: date
    maintenance_type: MaintenanceType = MaintenanceType.SERVICE
    description: str
    cost: float
    next_due_date: date | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EquipmentAssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Net Gun #2"])
    category: EquipmentCategory = EquipmentCategory.OTHER
    serial_number: str | None = Field(None, max_length=128)
    condition: EquipmentCondition = EquipmentCondition.GOOD
    notes: str | None = None


class EquipmentAssetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    category: EquipmentCategory | None = None
    serial_number: str | None = Field(None, max_length=128)
    condition: EquipmentCondition | None = None
    notes: str | None = None


class EquipmentAssetResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    serial_number: str | None
    condition: str
    notes: str | None
    current_checkout_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EquipmentCheckoutCreate(BaseModel):
    asset_id: uuid.UUID | None = None
    equipment_name: str = Field("", max_length=255, examples=["Net Gun"])
    assigned_to_agent_id: uuid.UUID | None = None
    assigned_to_vehicle_id: uuid.UUID | None = None
    expected_return_at: datetime | None = Field(
        None,
        examples=["2026-08-17T18:00:00Z"],
        description="When the equipment is due back. Defaults to a checkout window.",
    )
    notes: str | None = Field(None, examples=["Checked out for Sector 4 rescue."])


class EquipmentReturnRequest(BaseModel):
    notes: str | None = Field(None, examples=["Returned in good condition."])
    condition: EquipmentCondition | None = Field(
        None, description="Asset condition on return; updates the linked asset."
    )


class EquipmentCheckoutResponse(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID | None = None
    equipment_name: str
    assigned_to_agent_id: uuid.UUID | None
    assigned_to_vehicle_id: uuid.UUID | None
    rescue_dispatch_id: uuid.UUID | None = None
    checked_out_at: datetime
    expected_return_at: datetime | None
    returned_at: datetime | None
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FuelLogCreate(BaseModel):
    fuel_type: str = Field(..., min_length=1, max_length=32, examples=["Diesel"])
    volume_litres: float = Field(..., gt=0, examples=[45.5])
    cost: float = Field(..., ge=0, examples=[68.25])
    mileage_at_fill: int = Field(..., ge=0, examples=[12750])
    vendor: str | None = Field(None, max_length=255, examples=["Shell Gas Station"])
    receipt_url: str | None = Field(
        None, max_length=512, examples=["https://example.com/receipt.jpg"]
    )
    notes: str | None = Field(None, examples=["Full tank before long-distance dispatch."])


class FuelLogResponse(BaseModel):
    id: uuid.UUID
    vehicle_id: uuid.UUID
    filled_by_id: uuid.UUID | None
    fuel_type: str
    volume_litres: float
    cost: float
    mileage_at_fill: int
    vendor: str | None
    receipt_url: str | None
    notes: str | None
    filled_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BreakdownReportCreate(BaseModel):
    vehicle_id: uuid.UUID
    breakdown_type: str = Field(..., min_length=1, max_length=64, examples=["Engine failure"])
    severity: BreakdownSeverity = Field(BreakdownSeverity.MODERATE, examples=["critical"])
    description: str = Field(..., min_length=1, examples=["Vehicle stalled in transit."])
    location: str | None = Field(None, examples=["Main Street & 5th Ave"])
    driver_id: uuid.UUID | None = Field(None)
    notes: str | None = Field(None)


class BreakdownReportUpdate(BaseModel):
    breakdown_type: str | None = None
    severity: BreakdownSeverity | None = None
    description: str | None = None
    location: str | None = None
    status: BreakdownStatus | None = None
    resolved_at: datetime | None = None
    notes: str | None = None


class BreakdownReportResponse(BaseModel):
    id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None
    breakdown_type: str
    severity: str
    description: str
    location: str | None
    reported_at: datetime
    resolved_at: datetime | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FleetSummaryVehicle(BaseModel):
    id: uuid.UUID
    license_plate: str
    make_model: str
    due_date: date


class FleetSummaryResponse(BaseModel):
    total_vehicles: int
    by_status: dict[str, int]
    insurance_expiring: list[FleetSummaryVehicle]
    maintenance_due: list[FleetSummaryVehicle]
    outstanding_equipment: int
    overdue_equipment: int
    open_breakdowns: int
