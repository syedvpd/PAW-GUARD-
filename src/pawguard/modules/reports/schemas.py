from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


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


class ReportRequest(BaseModel):
    report_type: ReportType = Field(..., examples=["adoption"])
    format: ReportFormat = ReportFormat.PDF
    period_start: date | None = Field(None, examples=["2026-01-01"])
    period_end: date | None = Field(None, examples=["2026-07-31"])
    filters: dict[str, str] | None = Field(None, examples=[{"status": "completed"}])


class ReportResponse(BaseModel):
    report_type: ReportType
    format: ReportFormat
    filename: str
    content_type: str
    size_bytes: int
    download_url: str = Field(default="", description="Path to download the generated report")
