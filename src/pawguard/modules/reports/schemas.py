from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ReportFormat(StrEnum):
    PDF = "pdf"
    CSV = "csv"
    EXCEL = "xlsx"


class ReportType(StrEnum):
    DONATION = "donation"
    ADOPTION = "adoption"
    MEDICAL = "medical"
    INVENTORY = "inventory"
    RESCUE = "rescue"
    FINANCE = "finance"
    STAFF_PERFORMANCE = "staff_performance"
    ANIMAL_POPULATION = "animal_population"
    FOSTER = "foster"
    VOLUNTEER = "volunteer"
    SHELTER = "shelter"


class ReportRequest(BaseModel):
    report_type: ReportType = Field(..., examples=["adoption"])
    format: ReportFormat = ReportFormat.PDF
    period_start: date | None = Field(None, examples=["2026-01-01"])
    period_end: date | None = Field(None, examples=["2026-07-31"])
    filters: dict[str, str] | None = Field(None, examples=[{"status": "completed"}])

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            fmt = data.get("format")
            if isinstance(fmt, str):
                fmt_lower = fmt.lower().strip()
                if fmt_lower in ("excel", "xlsx", "xls"):
                    data["format"] = ReportFormat.EXCEL
                elif fmt_lower == "csv":
                    data["format"] = ReportFormat.CSV
                elif fmt_lower == "pdf":
                    data["format"] = ReportFormat.PDF
        return data

    @model_validator(mode="after")
    def _validate_date_range(self) -> "ReportRequest":
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_start > self.period_end
        ):
            raise ValueError("period_start must not be later than period_end")
        return self


class ReportResponse(BaseModel):
    report_type: ReportType
    format: ReportFormat
    filename: str
    content_type: str
    size_bytes: int
    download_url: str = Field(default="", description="Path to download the generated report")


class InventoryHealthAudit(BaseModel):
    total_catalog_items: str | int = 0
    total_inventory_value: str = "₹0.00"
    expired_product_value: str = "₹0.00"
    inventory_loss_write_off_value: str = "₹0.00"
    inventory_loss_rate_pct: str = "0.0%"
    stock_movement_speed: str = "N/A"
    check_in_out_volume: str = "0.0"
    upcoming_purchase_order_requirements_exposure: str = "₹0.00"


class PurchaseOrderItemRequirement(BaseModel):
    item_id: str
    name: str
    category: str | None = None
    current_stock: float = 0.0
    reorder_threshold: float = 0.0
    suggested_order_qty: float = 0.0
    unit: str = "units"
    unit_cost: float = 0.0
    estimated_cost: float = 0.0


class UpcomingPurchaseOrderRequirements(BaseModel):
    items: list[PurchaseOrderItemRequirement] = Field(default_factory=list)


class ExpiredProductItem(BaseModel):
    item_id: str
    name: str
    category: str | None = None
    expired_qty: float = 0.0
    expiry_date: str | None = None
    unit_cost: float = 0.0
    loss_value: float = 0.0
    status: str = "EXPIRED"


class ExpiredProductValuesAudit(BaseModel):
    items: list[ExpiredProductItem] = Field(default_factory=list)


class StockMovementRecord(BaseModel):
    reference_type: str
    check_in_qty: float = 0.0
    check_out_qty: float = 0.0
    adjustment_qty: float = 0.0
    movement_count: int = 0


class StockMovementSummary(BaseModel):
    records: list[StockMovementRecord] = Field(default_factory=list)


class RequisitionItemRecord(BaseModel):
    requisition_id: str
    item_id: str
    quantity: float = 0.0
    status: str


class PendingPurchaseRequisitions(BaseModel):
    requisitions: list[RequisitionItemRecord] = Field(default_factory=list)


class InventoryReportSections(BaseModel):
    inventory_health_and_loss_audit: InventoryHealthAudit = Field(
        default_factory=InventoryHealthAudit
    )
    upcoming_purchase_order_requirements: UpcomingPurchaseOrderRequirements = Field(
        default_factory=UpcomingPurchaseOrderRequirements
    )
    expired_product_values_audit: ExpiredProductValuesAudit = Field(
        default_factory=ExpiredProductValuesAudit
    )
    stock_movement_and_usage_summary: StockMovementSummary = Field(
        default_factory=StockMovementSummary
    )
    pending_purchase_requisition_orders: PendingPurchaseRequisitions = Field(
        default_factory=PendingPurchaseRequisitions
    )


class InventoryReportDetails(BaseModel):
    title: str = "Inventory Consumption & Expiry Audit"
    generated_at: str | None = None
    sections: InventoryReportSections


class InventoryAnalyticsResponse(BaseModel):
    report_type: str = "inventory"
    report: InventoryReportDetails


class ReportAnalyticsRequest(BaseModel):
    report_type: ReportType = Field(default=ReportType.INVENTORY, examples=["inventory"])
    filters: dict[str, str] | None = Field(None, examples=[{"category": "medical"}])
