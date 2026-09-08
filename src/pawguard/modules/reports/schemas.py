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
