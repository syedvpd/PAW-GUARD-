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
    movement_type: MovementType = Field(..., examples=["check_in"])
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


class SupplierCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, examples=["MedSupply Co."])
    contact_person: str | None = Field(None, max_length=255, examples=["Rajesh Kumar"])
    email: str | None = Field(None, max_length=255, examples=["contact@medsupply.com"])
    phone: str | None = Field(None, max_length=64, examples=["+91-98765-43210"])
    address: str | None = Field(None, examples=["123 Industrial Area, City, State"])
    gst_number: str | None = Field(None, max_length=64, examples=["29ABCDE1234F1Z5"])
    pan_number: str | None = Field(None, max_length=20, examples=["ABCDE1234F"])
    bank_details: str | None = Field(None, examples=["HDFC Bank, Acc: 1234567890"])
    payment_terms: str | None = Field(None, max_length=255, examples=["Net 30 days"])
    notes: str | None = Field(None, examples=["Preferred vendor for vaccines."])


class SupplierUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    contact_person: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=64)
    address: str | None = None
    gst_number: str | None = Field(None, max_length=64)
    pan_number: str | None = Field(None, max_length=20)
    bank_details: str | None = None
    payment_terms: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    notes: str | None = None


class SupplierResponse(BaseModel):
    id: uuid.UUID
    name: str
    contact_person: str | None
    email: str | None
    phone: str | None
    address: str | None
    gst_number: str | None
    pan_number: str | None
    bank_details: str | None
    payment_terms: str | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryItemSupplierCreate(BaseModel):
    item_id: uuid.UUID
    supplier_id: uuid.UUID
    unit_cost: float = Field(..., gt=0.0, examples=[4.50])
    lead_time_days: int | None = Field(None, ge=0, examples=[7])
    is_preferred: bool = Field(False, examples=[True])


class InventoryItemSupplierResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    supplier_id: uuid.UUID
    unit_cost: float
    lead_time_days: int | None
    is_preferred: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
