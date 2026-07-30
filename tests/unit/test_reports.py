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
