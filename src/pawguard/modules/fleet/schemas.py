"""Pydantic schemas for fleet management."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.fleet.models import VehicleStatus


class VehicleCreate(BaseModel):
    make_model: str = Field(..., min_length=1, max_length=255)
    license_plate: str = Field(..., min_length=1, max_length=64)
    status: VehicleStatus = VehicleStatus.ACTIVE
    mileage: int = Field(0, ge=0)
    primary_driver_id: uuid.UUID | None = None


class VehicleUpdate(BaseModel):
    make_model: str | None = Field(None, min_length=1, max_length=255)
    license_plate: str | None = Field(None, min_length=1, max_length=64)
    status: VehicleStatus | None = None
    mileage: int | None = Field(None, ge=0)
    primary_driver_id: uuid.UUID | None = None


class VehicleStatusUpdate(BaseModel):
    status: VehicleStatus = Field(..., description="New status for the vehicle")


class VehicleResponse(BaseModel):
    id: uuid.UUID
    make_model: str
    license_plate: str
    status: VehicleStatus
    mileage: int
    primary_driver_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaintenanceCreate(BaseModel):
    vehicle_id: uuid.UUID
    service_date: date
    description: str = Field(..., min_length=1)
    cost: float = Field(0.0, ge=0.0)
    next_due_date: date | None = None


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
    equipment_name: str = Field(..., min_length=1, max_length=255)
    assigned_to_agent_id: uuid.UUID | None = None
    assigned_to_vehicle_id: uuid.UUID | None = None
    notes: str | None = None


class EquipmentReturnRequest(BaseModel):
    notes: str | None = None


class EquipmentCheckoutResponse(BaseModel):
    id: uuid.UUID
    equipment_name: str
    assigned_to_agent_id: uuid.UUID | None
    assigned_to_vehicle_id: uuid.UUID | None
    checked_out_at: datetime
    returned_at: datetime | None
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
