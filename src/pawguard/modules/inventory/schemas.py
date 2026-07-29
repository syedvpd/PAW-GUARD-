"""Pydantic schemas for the Inventory module."""

import uuid
from datetime import date, datetime
from pydantic import BaseModel, Field, ConfigDict

from pawguard.modules.inventory.models import ItemCategory, MovementType, RequisitionStatus


class InventoryItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: ItemCategory
    quantity: float = Field(0.0, ge=0.0)
    unit: str = Field(..., min_length=1, max_length=32)
    reorder_threshold: float = Field(10.0, ge=0.0)
    expiry_date: date | None = None


class InventoryItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: ItemCategory
    quantity: float
    unit: str
    reorder_threshold: float
    expiry_date: date | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryMovementCreate(BaseModel):
    item_id: uuid.UUID
    movement_type: MovementType
    quantity: float = Field(..., gt=0.0)
    notes: str | None = None


class InventoryMovementResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    moved_by: uuid.UUID
    movement_type: MovementType
    quantity: float
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequisitionOrderCreate(BaseModel):
    item_id: uuid.UUID
    quantity: float = Field(..., gt=0.0)


class RequisitionOrderResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    requester_id: uuid.UUID
    quantity: float
    status: RequisitionStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
