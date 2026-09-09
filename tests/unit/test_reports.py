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
            ReportType.DONATION,
            ReportFormat.CSV,
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
            ReportType.DONATION,
            ReportFormat.PDF,
        )
        assert result["format"] == "pdf"
        assert result["content_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_generate_excel_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION,
            ReportFormat.EXCEL,
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
            ReportType.DONATION,
            ReportFormat.CSV,
        )
        assert result["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_adoption_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.ADOPTION,
            ReportFormat.CSV,
        )
        assert result["report_type"] == "adoption"

    @pytest.mark.asyncio
    async def test_medical_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.MEDICAL,
            ReportFormat.CSV,
        )
        assert result["report_type"] == "medical"

    @pytest.mark.asyncio
    async def test_inventory_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.INVENTORY,
            ReportFormat.CSV,
        )
        assert result["report_type"] == "inventory"

    @pytest.mark.asyncio
    async def test_rescue_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.RESCUE,
            ReportFormat.CSV,
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
        mock_result.all.return_value = [(located, None), (unlocated, None)]
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
        mock_result.all.return_value = [(unlocated, None)]
        mock_session.execute.return_value = mock_result

        result = await service._rescue_report(None, None, None)

        assert not any("Geo Heatmap" in sec["title"] for sec in result["sections"])

    @pytest.mark.asyncio
    async def test_finance_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.FINANCE,
            ReportFormat.CSV,
        )
        assert result["report_type"] == "finance"

    @pytest.mark.asyncio
    async def test_animal_population_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.ANIMAL_POPULATION,
            ReportFormat.CSV,
        )
        assert result["report_type"] == "animal_population"

    @pytest.mark.asyncio
    async def test_foster_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.FOSTER,
            ReportFormat.CSV,
        )
        assert result["report_type"] == "foster"

    @pytest.mark.asyncio
    async def test_volunteer_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.VOLUNTEER,
            ReportFormat.CSV,
        )
        assert result["report_type"] == "volunteer"

    @pytest.mark.asyncio
    async def test_shelter_report(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.SHELTER,
            ReportFormat.CSV,
        )
        assert result["report_type"] == "shelter"

    @pytest.mark.asyncio
    async def test_shelter_report_with_data(self, service, mock_session):
        mock_facility = MagicMock()
        mock_facility.id = "fac-1"
        mock_facility.name = "Main Shelter"
        mock_facility.status = "active"
        mock_facility.facility_type = "shelter"
        mock_facility.total_capacity = 100
        mock_facility.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_facility]
        mock_session.execute.return_value = mock_result

        result = await service._shelter_report(None, None, None)
        assert result["title"] == "Shelter Capacity & Turnover Audit Report"
        assert len(result["rows"]) == 1
        assert result["rows"][0][1] == "Main Shelter"

    @pytest.mark.asyncio
    async def test_shelter_report_sections(self, service, mock_session):
        mock_facility = MagicMock()
        mock_facility.id = "fac-1"
        mock_facility.name = "Main Shelter"
        mock_facility.status = "active"
        mock_facility.facility_type = "shelter"
        mock_facility.total_capacity = 100
        mock_facility.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_facility]
        mock_session.execute.return_value = mock_result

        result = await service._shelter_report(None, None, None)
        assert "sections" in result
        section_titles = [s["title"] for s in result["sections"]]
        assert "Shelter Capacity & Turnover Audit Summary" in section_titles
        assert "Kennel Capacity & Utilization by Facility" in section_titles
        assert "Inter-Facility Transfer Volumes" in section_titles

    @pytest.mark.asyncio
    async def test_rep_001_rescue_operational_efficiency_metrics(self, service, mock_session):
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        req = MagicMock()
        req.id = "req-1"
        req.ticket_number = "RC-100"
        req.status = "rescued"
        req.reporter_name = "Reporter X"
        req.location_address = "Sector 14"
        req.animal_count = 1
        req.created_at = now - timedelta(hours=2)
        req.latitude = 12.97
        req.longitude = 77.59

        disp = MagicMock()
        disp.id = "disp-1"
        disp.rescue_request_id = "req-1"
        disp.dispatched_at = now - timedelta(hours=1, minutes=45)
        disp.located_at = now - timedelta(hours=1)
        disp.failure_reason = None
        disp.assigned_driver_id = "driver-1"
        disp.vehicle_id = "VH-01"

        mock_result = MagicMock()
        mock_result.all.return_value = [(req, disp)]
        mock_session.execute.return_value = mock_result

        result = await service._rescue_report(None, None, None)
        assert result["title"] == "Rescue Operational Efficiency Report"
        section_titles = [s["title"] for s in result["sections"]]
        assert "Dispatch & Response Analytics" in section_titles
        analytics_sec = next(
            s for s in result["sections"] if s["title"] == "Dispatch & Response Analytics"
        )
        metrics_dict = {row[0]: row[1] for row in analytics_sec["rows"]}
        assert "Successful Rescue Ratio" in metrics_dict
        assert "Avg Response Time (Incident to On-Site Arrival)" in metrics_dict
        assert "Avg Response Time (Incident to Dispatch)" in metrics_dict

    @pytest.mark.asyncio
    async def test_rep_003_medical_compliance_metrics(self, service, mock_session):
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        mock_treatment = MagicMock()
        mock_treatment.id = "treat-1"
        mock_treatment.dog_id = "dog-1"
        mock_treatment.vet_id = "vet-1"
        mock_treatment.treatment_type = "Routine Checkup"
        mock_treatment.treatment_date = now
        mock_treatment.post_op_notes = "Normal"

        mock_vax = MagicMock()
        mock_vax.dog_id = "dog-1"
        mock_vax.vaccine_name = "Rabies"
        mock_vax.administered_at = now
        mock_vax.next_due_at = now + datetime.resolution

        mock_session.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[mock_treatment]))
                )
            ),
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_vax])))
            ),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(scalar=MagicMock(return_value=500.0)),
        ]

        result = await service._medical_report(None, None, None)
        assert result["title"] == "Medical Care & Immunization Compliance Report"
        section_titles = [s["title"] for s in result["sections"]]
        assert "Medical Care & Immunization Compliance Summary" in section_titles
        assert "Veterinary Expenditure Analysis" in section_titles
        summary_sec = next(
            s
            for s in result["sections"]
            if s["title"] == "Medical Care & Immunization Compliance Summary"
        )
        metrics = {row[0]: row[1] for row in summary_sec["rows"]}
        assert "Vaccination Coverage Rate" in metrics
        assert "Follow-up Exam Compliance Rate" in metrics
        assert "Total Veterinary Expenditure per Dog" in metrics

    @pytest.mark.asyncio
    async def test_rep_004_inventory_loss_and_po_requirements(self, service, mock_session):
        item = MagicMock()
        item.id = "item-1"
        item.name = "Bandages"
        item.category = "Consumables"
        item.quantity = 5.0
        item.reorder_threshold = 10.0
        item.unit = "boxes"
        item.unit_cost = 20.0
        item.expiry_date = None

        mock_session.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[item])))
            ),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ]

        result = await service._inventory_report(None)
        assert result["title"] == "Inventory Consumption & Expiry Audit Report"
        section_titles = [s["title"] for s in result["sections"]]
        assert "Inventory Health & Loss Audit" in section_titles
        assert any("Upcoming Purchase Order Requirements" in t for t in section_titles)
        health_sec = next(
            s for s in result["sections"] if s["title"] == "Inventory Health & Loss Audit"
        )
        metrics = {row[0]: row[1] for row in health_sec["rows"]}
        assert "Inventory Loss Rate" in metrics
        assert "Stock Movement Speed (Avg Interval)" in metrics
        assert "Upcoming Purchase Order Requirements Exposure" in metrics

    @pytest.mark.asyncio
    async def test_rep_005_report_format_normalization(self):
        from pawguard.modules.reports.schemas import ReportRequest

        req_excel = ReportRequest(report_type=ReportType.RESCUE, format="excel")
        assert req_excel.format == ReportFormat.EXCEL

        req_xlsx = ReportRequest(report_type=ReportType.RESCUE, format="xlsx")
        assert req_xlsx.format == ReportFormat.EXCEL

        req_csv = ReportRequest(report_type=ReportType.RESCUE, format="CSV")
        assert req_csv.format == ReportFormat.CSV

        req_pdf = ReportRequest(report_type=ReportType.RESCUE, format="PDF")
        assert req_pdf.format == ReportFormat.PDF

    @pytest.mark.asyncio
    async def test_download_url_in_response(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION,
            ReportFormat.CSV,
        )
        assert result["download_url"].startswith("/api/v1/reports/download/")
        assert result["filename"].endswith(".csv")

    @pytest.mark.asyncio
    async def test_report_with_period_filters(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = await service.generate_report(
            ReportType.DONATION,
            ReportFormat.CSV,
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
            ReportType.DONATION,
            ReportFormat.CSV,
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
        mock_result.all.return_value = [(mock_rescue, None)]
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
        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar=MagicMock(return_value=v))
                for v in [42, 12, 20, 15, 8, 3.5, 25, 50, 45.2, 30]
            ]
        )
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


class TestReportPermissionsInSeed:
    def test_operational_staff_roles_hold_report_permissions(self):
        from scripts.seed_roles_and_permissions import ROLE_DEFINITIONS

        from pawguard.modules.auth import permission_codes as pc

        role_map = {name: set(perms) for name, _, _, perms in ROLE_DEFINITIONS}
        operational_roles = [
            "super_admin",
            "rescue_centre_admin",
            "rescue_coordinator",
            "veterinarian",
            "shelter_manager",
            "adoption_coordinator",
            "foster_coordinator",
            "volunteer_coordinator",
            "inventory_manager",
            "finance_user",
        ]

        for role_name in operational_roles:
            assert role_name in role_map, f"Role {role_name} missing from ROLE_DEFINITIONS"
            perms = role_map[role_name]
            assert pc.REPORTS_READ in perms, f"{role_name} missing {pc.REPORTS_READ}"
            assert pc.REPORTS_CREATE in perms, f"{role_name} missing {pc.REPORTS_CREATE}"
            assert pc.REPORTS_EXPORT_PDF in perms, f"{role_name} missing {pc.REPORTS_EXPORT_PDF}"
            assert pc.REPORTS_EXPORT_CSV in perms, f"{role_name} missing {pc.REPORTS_EXPORT_CSV}"
            assert pc.REPORTS_EXPORT_EXCEL in perms, (
                f"{role_name} missing {pc.REPORTS_EXPORT_EXCEL}"
            )


class TestInventoryReportRegression:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        return ReportService(mock_session)

    @pytest.mark.asyncio
    async def test_inventory_report_single_movement_does_not_raise_zip_error(
        self, service, mock_session
    ):
        """Regression test: zip(timestamps, timestamps[1:]) with 1 movement must not raise

        ValueError: zip() argument 2 is shorter than argument 1.
        """
        import uuid
        from datetime import UTC, datetime

        from pawguard.modules.inventory.models import InventoryItem, InventoryMovement, MovementType

        item = InventoryItem(
            id=uuid.uuid4(),
            name="Bandages",
            category="medical",
            quantity=10.0,
            unit="box",
            reorder_threshold=5.0,
            unit_cost=15.0,
            expiry_date=None,
        )
        movement = InventoryMovement(
            id=uuid.uuid4(),
            item_id=item.id,
            movement_type=MovementType.CHECK_IN,
            quantity=10.0,
            reference_type="purchase",
            created_at=datetime.now(UTC),
        )

        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[item])))
                ),
                MagicMock(
                    scalars=MagicMock(
                        return_value=MagicMock(all=MagicMock(return_value=[movement]))
                    )
                ),
                MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
                ),
            ]
        )

        result = await service._inventory_report(None)
        assert result["title"] == "Inventory Consumption & Expiry Audit Report"
        assert len(result["sections"]) >= 2
        section_titles = [s["title"] for s in result["sections"]]
        assert "Inventory Health & Loss Audit" in section_titles
        assert "Stock Movement & Usage Summary" in section_titles

    @pytest.mark.asyncio
    async def test_inventory_report_empty_dataset(self, service, mock_session):
        """Empty dataset must return clean valid report with zero/empty sections without error."""
        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
                ),
                MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
                ),
                MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
                ),
            ]
        )

        result = await service._inventory_report(None)
        assert result["title"] == "Inventory Consumption & Expiry Audit Report"
        assert len(result["sections"]) >= 1
        assert result["sections"][0]["title"] == "Inventory Health & Loss Audit"

    @pytest.mark.asyncio
    async def test_inventory_report_with_expired_and_reorder_items(self, service, mock_session):
        import uuid
        from datetime import UTC, date, datetime, timedelta

        from pawguard.modules.inventory.models import (
            InventoryItem,
            InventoryMovement,
            MovementType,
            RequisitionOrder,
            RequisitionStatus,
        )

        expired_item = InventoryItem(
            id=uuid.uuid4(),
            name="Old Vaccine",
            category="medical",
            quantity=5.0,
            unit="vial",
            reorder_threshold=10.0,  # Below threshold
            unit_cost=50.0,
            expiry_date=date.today() - timedelta(days=5),
        )
        movement1 = InventoryMovement(
            id=uuid.uuid4(),
            item_id=expired_item.id,
            movement_type=MovementType.CHECK_IN,
            quantity=10.0,
            reference_type="purchase",
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
        movement2 = InventoryMovement(
            id=uuid.uuid4(),
            item_id=expired_item.id,
            movement_type=MovementType.ADJUSTMENT,
            quantity=-5.0,
            reference_type="waste",
            created_at=datetime.now(UTC),
        )
        req = RequisitionOrder(
            id=uuid.uuid4(),
            item_id=expired_item.id,
            quantity=15.0,
            status=RequisitionStatus.PENDING,
        )

        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(
                    scalars=MagicMock(
                        return_value=MagicMock(all=MagicMock(return_value=[expired_item]))
                    )
                ),
                MagicMock(
                    scalars=MagicMock(
                        return_value=MagicMock(all=MagicMock(return_value=[movement1, movement2]))
                    )
                ),
                MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[req])))
                ),
            ]
        )

        result = await service._inventory_report(None)
        section_titles = [s["title"] for s in result["sections"]]
        assert "Inventory Health & Loss Audit" in section_titles
        assert (
            "Upcoming Purchase Order Requirements (Items Below Reorder Threshold)" in section_titles
        )
        assert "Expired Product Values Audit" in section_titles
        assert "Stock Movement & Usage Summary" in section_titles
        assert "Pending Purchase Requisition Orders" in section_titles

    @pytest.mark.asyncio
    async def test_generate_inventory_report_endpoint_success(self):
        import uuid
        from datetime import UTC, datetime

        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from pawguard.core.security import AccessTokenClaims
        from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
        from pawguard.modules.auth.models import Permission, Role, User
        from pawguard.modules.reports.router import get_report_service
        from pawguard.modules.reports.router import router as reports_router

        test_app = FastAPI()
        test_app.include_router(reports_router, prefix="/api/v1")

        mock_svc = AsyncMock()
        mock_svc.generate_report.return_value = {
            "title": "Inventory Consumption & Expiry Audit Report",
            "report_type": "inventory",
            "format": "pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
            "filename": "inventory_report.pdf",
            "download_url": "/api/v1/reports/download/inventory_report.pdf",
            "generated_at": "2026-09-09T04:00:00Z",
            "sections": [
                {
                    "title": "Inventory Health & Loss Audit",
                    "headers": ["Metric", "Value"],
                    "rows": [["Total Items", "10"]],
                },
                {
                    "title": "Upcoming Purchase Order Requirements",
                    "headers": ["Item ID", "Name", "Required Qty"],
                    "rows": [["1", "Vaccines", "5"]],
                },
                {
                    "title": "Expired Product Values Audit",
                    "headers": ["Name", "Loss Value"],
                    "rows": [["Old Serum", "₹500"]],
                },
            ],
            "headers": ["ID", "Name"],
            "rows": [["1", "Vaccine"]],
        }

        now = datetime.now(UTC)
        role = Role(
            id=uuid.uuid4(),
            name="inventory_manager",
            description="Inventory Manager",
            is_system=True,
            created_at=now,
            updated_at=now,
        )
        perm = Permission(
            id=uuid.uuid4(),
            code="reports:create",
            description="Create Reports",
            created_at=now,
            updated_at=now,
        )
        role.permissions = [perm]
        user = User(
            id=uuid.uuid4(),
            email="inventory.manager@pawguard.com",
            hashed_password="hash",
            full_name="Inventory Manager",
            phone="1234567890",
            is_active=True,
            is_verified=True,
            mfa_enabled=False,
            created_at=now,
            updated_at=now,
        )
        user.roles = [role]

        claims = AccessTokenClaims(
            user_id=user.id,
            session_id=uuid.uuid4(),
            roles=["inventory_manager"],
            jti="jti",
            expires_at=now,
        )
        import json

        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(["reports:create", "reports:read"])
        mock_redis.set.return_value = True

        mock_db = AsyncMock()
        mock_db_result = MagicMock()
        mock_db_result.scalars.return_value.all.return_value = ["reports:create", "reports:read"]
        mock_db.execute.return_value = mock_db_result

        mock_current_user = CurrentUser(
            user=user,
            claims=claims,
            db=mock_db,
            redis=mock_redis,
        )

        for route in test_app.routes:
            if getattr(route, "path", None) == "/api/v1/reports/generate":
                for dep in getattr(route, "dependencies", []):
                    test_app.dependency_overrides[dep.dependency] = lambda: mock_current_user

        test_app.dependency_overrides[get_current_user] = lambda: mock_current_user
        test_app.dependency_overrides[get_report_service] = lambda: mock_svc

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/reports/generate",
                json={"report_type": "inventory"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert data["data"]["report_type"] == "inventory"
            assert data["data"]["filename"] == "inventory_report.pdf"
            assert data["data"]["download_url"] == "/api/v1/reports/download/inventory_report.pdf"
