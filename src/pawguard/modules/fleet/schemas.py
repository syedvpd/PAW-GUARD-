"""Pydantic schemas for fleet management."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.fleet.models import VehicleStatus, VehicleType


class VehicleCreate(BaseModel):
    make_model: str = Field(..., min_length=1, max_length=255, examples=["Ford Transit 2022"])
    license_plate: str = Field(..., min_length=1, max_length=64, examples=["RESCUE-01"])
    vehicle_type: VehicleType = VehicleType.RESCUE_VAN
    status: VehicleStatus = VehicleStatus.ACTIVE
    mileage: int = Field(0, ge=0, examples=[12500])
    primary_driver_id: uuid.UUID | None = None


class VehicleUpdate(BaseModel):
    make_model: str | None = Field(
        None, min_length=1, max_length=255, examples=["Ford Transit 2022"]
    )
    license_plate: str | None = Field(None, min_length=1, max_length=64, examples=["RESCUE-01"])
    vehicle_type: VehicleType | None = Field(None, examples=["ambulance"])
    status: VehicleStatus | None = Field(None, examples=["active"])
    mileage: int | None = Field(None, ge=0, examples=[12800])
    primary_driver_id: uuid.UUID | None = None
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
    description: str = Field(..., min_length=1, examples=["Oil change and brake inspection"])
    cost: float = Field(0.0, ge=0.0, examples=[150.0])
    next_due_date: date | None = Field(None, examples=["2027-01-15"])


class MaintenanceResponse(BaseModel):
    id: uuid.UUID
    vehicle_id: uuid.UUID
    service_date: date
    description: str
    cost: float
    next_due_date: date | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EquipmentCheckoutCreate(BaseModel):
    equipment_name: str = Field(..., min_length=1, max_length=255, examples=["Net Gun"])
    assigned_to_agent_id: uuid.UUID | None = None
    assigned_to_vehicle_id: uuid.UUID | None = None
    expected_return_at: datetime | None = Field(
        None, examples=["2026-08-17T18:00:00Z"],
        description="When the equipment is due back. Defaults to a checkout window.",
    )
    notes: str | None = Field(None, examples=["Checked out for Sector 4 rescue."])


class EquipmentReturnRequest(BaseModel):
    notes: str | None = Field(None, examples=["Returned in good condition."])


class EquipmentCheckoutResponse(BaseModel):
    id: uuid.UUID
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
    receipt_url: str | None = Field(None, max_length=512, examples=["https://example.com/receipt.jpg"])
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
