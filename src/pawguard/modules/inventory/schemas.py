"""Pydantic schemas for the Inventory module."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.inventory.models import ItemCategory, MovementType, RequisitionStatus


class InventoryItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Rabies Vaccine"])
    category: ItemCategory = Field(..., examples=["vaccine"])
    quantity: float = Field(0.0, ge=0.0, examples=[50.0])
    unit: str = Field(..., min_length=1, max_length=32, examples=["vial"])
    reorder_threshold: float = Field(10.0, ge=0.0, examples=[10.0])
    expiry_date: date | None = Field(None, examples=["2027-03-01"])
    unit_cost: float = Field(0.0, ge=0.0, examples=[4.50])


class InventoryItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: ItemCategory
    quantity: float
    unit: str
    reorder_threshold: float
    expiry_date: date | None
    unit_cost: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryMovementCreate(BaseModel):
    item_id: uuid.UUID
    movement_type: MovementType = Field(..., examples=["consumption"])
    quantity: float = Field(..., gt=0.0, examples=[5.0])
    notes: str | None = Field(None, examples=["Used during morning treatment rounds."])
    reference_type: str | None = Field(None, examples=["medical_treatment"])
    reference_id: uuid.UUID | None = None


class InventoryConsumptionItem(BaseModel):
    """Optional stock draw-down attached to a treatment/care-log request."""

    item_id: uuid.UUID = Field(..., examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    quantity: float = Field(..., gt=0.0, examples=[2.0])


class InventoryMovementResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    moved_by: uuid.UUID
    movement_type: MovementType
    quantity: float
    notes: str | None
    reference_type: str | None
    reference_id: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequisitionOrderCreate(BaseModel):
    item_id: uuid.UUID
    quantity: float = Field(..., gt=0.0, examples=[100.0])


class RequisitionOrderResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    requester_id: uuid.UUID
    quantity: float
    status: RequisitionStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255, examples=["Rabies Vaccine"])
    category: ItemCategory | None = Field(None, examples=["vaccine"])
    quantity: float | None = Field(None, ge=0.0, examples=[45.0])
    unit: str | None = Field(None, min_length=1, max_length=32, examples=["vial"])
    reorder_threshold: float | None = Field(None, ge=0.0, examples=[15.0])
    expiry_date: date | None = Field(None, examples=["2027-03-01"])
    unit_cost: float | None = Field(None, ge=0.0, examples=[4.75])


class RequisitionStatusUpdate(BaseModel):
    status: RequisitionStatus = Field(..., examples=["approved"])
