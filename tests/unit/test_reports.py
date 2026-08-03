"""Unit tests for ReportService with mocked session."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.modules.reports.schemas import ReportFormat, ReportType
from pawguard.modules.reports.service import ReportService


class TestReportService:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        return ReportService(mock_session)

    @pytest.mark.asyncio
    async def test_generate_csv_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION, ReportFormat.CSV,
        )
        assert result["format"] == "csv"
        assert result["report_type"] == "donation"
        assert result["content_type"] == "text/csv"

    @pytest.mark.asyncio
    async def test_generate_pdf_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION, ReportFormat.PDF,
        )
        assert result["format"] == "pdf"
        assert result["content_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_generate_excel_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION, ReportFormat.EXCEL,
        )
        assert result["format"] == "xlsx"

    @pytest.mark.asyncio
    async def test_donation_report_with_data(self, service, mock_session):
        mock_donation = MagicMock()
        mock_donation.id = "don-1"
        mock_donation.donor_id = "usr-1"
        mock_donation.amount = 100.0
        mock_donation.currency = "USD"
        mock_donation.donation_type = "one_time"
        mock_donation.status = "success"
        mock_donation.created_at.date.return_value = "2026-07-01"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_donation]
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION, ReportFormat.CSV,
        )
        assert result["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_adoption_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.ADOPTION, ReportFormat.CSV,
        )
        assert result["report_type"] == "adoption"

    @pytest.mark.asyncio
    async def test_medical_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.MEDICAL, ReportFormat.CSV,
        )
        assert result["report_type"] == "medical"

    @pytest.mark.asyncio
    async def test_inventory_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.INVENTORY, ReportFormat.CSV,
        )
        assert result["report_type"] == "inventory"

    @pytest.mark.asyncio
    async def test_rescue_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.RESCUE, ReportFormat.CSV,
        )
        assert result["report_type"] == "rescue"

    @pytest.mark.asyncio
    async def test_rescue_report_geo_heatmap_section(self, service, mock_session):
        located = MagicMock()
        located.id = "res-1"
        located.ticket_number = "RC-0001"
        located.status = "pending"
        located.reporter_name = "Alice"
        located.location_address = "Main St"
        located.animal_count = 2
        located.created_at.date.return_value = "2026-07-01"
        located.latitude = 17.4482
        located.longitude = 78.3741
        unlocated = MagicMock()
        unlocated.id = "res-2"
        unlocated.ticket_number = "RC-0002"
        unlocated.status = "pending"
        unlocated.reporter_name = "Bob"
        unlocated.location_address = "Nowhere"
        unlocated.animal_count = 1
        unlocated.created_at.date.return_value = "2026-07-02"
        unlocated.latitude = None
        unlocated.longitude = None
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [located, unlocated]
        mock_session.execute.return_value = mock_result

        result = await service._rescue_report(None, None, None)

        assert result["sections"], "expected a geo heatmap section"
        section = result["sections"][0]
        assert section["title"].startswith("Geo Heatmap (Rescue Locations)")
        assert "1 case(s) without coordinates" in section["title"]
        assert section["headers"] == ["Latitude", "Longitude", "Cases"]
        assert section["rows"] == [["17.45", "78.37", 1]]

    @pytest.mark.asyncio
    async def test_rescue_report_no_geo_section_when_no_coords(self, service, mock_session):
        unlocated = MagicMock()
        unlocated.id = "res-1"
        unlocated.ticket_number = "RC-0001"
        unlocated.status = "pending"
        unlocated.reporter_name = "Alice"
        unlocated.location_address = "Nowhere"
        unlocated.animal_count = 2
        unlocated.created_at.date.return_value = "2026-07-01"
        unlocated.latitude = None
        unlocated.longitude = None
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [unlocated]
        mock_session.execute.return_value = mock_result

        result = await service._rescue_report(None, None, None)

        assert result["sections"] == []

    @pytest.mark.asyncio
    async def test_finance_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.FINANCE, ReportFormat.CSV,
        )
        assert result["report_type"] == "finance"

    @pytest.mark.asyncio
    async def test_animal_population_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.ANIMAL_POPULATION, ReportFormat.CSV,
        )
        assert result["report_type"] == "animal_population"

    @pytest.mark.asyncio
    async def test_foster_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.FOSTER, ReportFormat.CSV,
        )
        assert result["report_type"] == "foster"

    @pytest.mark.asyncio
    async def test_volunteer_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.VOLUNTEER, ReportFormat.CSV,
        )
        assert result["report_type"] == "volunteer"

    @pytest.mark.asyncio
    async def test_staff_performance_report(self, service, mock_session):
        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar=MagicMock(return_value=v)) for v in [0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        ])
        result = await service.generate_report(
            ReportType.STAFF_PERFORMANCE, ReportFormat.CSV,
        )
        assert result["report_type"] == "staff_performance"

    @pytest.mark.asyncio
    async def test_download_url_in_response(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION, ReportFormat.CSV,
        )
        assert result["download_url"].startswith("/api/v1/reports/download/")
        assert result["filename"].endswith(".csv")

    @pytest.mark.asyncio
    async def test_report_with_period_filters(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION, ReportFormat.CSV,
            period_start="2026-01-01",
            period_end="2026-06-30",
        )
        assert result["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_report_with_custom_filters(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION, ReportFormat.CSV,
            filters={"status": "success"},
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_rescue_report_with_pii_masking(self, service, mock_session):
        mock_rescue = MagicMock()
        mock_rescue.id = "res-1"
        mock_rescue.ticket_number = "TKT-001"
        mock_rescue.status = "reported"
        mock_rescue.reporter_name = "John Smith"
        mock_rescue.location_address = "123 Main St"
        mock_rescue.animal_count = 2
        mock_rescue.created_at.date.return_value = "2026-07-01"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_rescue]
        mock_session.execute.return_value = mock_result
        result = await service._rescue_report(None, None, None)
        row = result["rows"][0]
        assert row[3] != "John Smith"
        assert "***" in row[3]


class TestStaffPerformanceReport:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        return ReportService(mock_session)

    @pytest.mark.asyncio
    async def test_staff_performance_report_returns_metrics(self, service, mock_session):
        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar=MagicMock(return_value=v))
            for v in [42, 12, 20, 15, 8, 3.5, 25, 50, 45.2, 30]
        ])
        result = await service._staff_performance_report(None, None, None)
        assert result["title"] == "Staff Performance Report"
        assert result["headers"] == ["Metric", "Value"]
        assert len(result["rows"]) == 10
        metric_names = [r[0] for r in result["rows"]]
        assert "Total Adoptions" in metric_names
        assert "Adoption Velocity" in metric_names
        assert "Active Foster Placements" in metric_names
        assert "Foster Efficiency Rate" in metric_names
        assert "Rescue Response Count" in metric_names
        assert "Avg Rescue Response Time" in metric_names
        assert "Medical Treatments This Period" in metric_names
        assert "Total Dogs in Care" in metric_names
        assert "Avg Length of Stay" in metric_names
        assert "Volunteer Hours" in metric_names
