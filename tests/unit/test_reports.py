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


class TestInventoryAnalyticsEndpointsAndService:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        return ReportService(mock_session)

    @pytest.mark.asyncio
    async def test_inventory_analytics_populated_data(self, service, mock_session):
        """1. Populated inventory data with multiple items, movements, expired items, and requisitions."""
        import uuid
        from datetime import UTC, date, datetime, timedelta

        from pawguard.modules.inventory.models import (
            InventoryItem,
            InventoryMovement,
            MovementType,
            RequisitionOrder,
            RequisitionStatus,
        )

        item1 = InventoryItem(
            id=uuid.uuid4(),
            name="Rabies Vaccine",
            category="medical",
            quantity=5.0,
            unit="vials",
            reorder_threshold=20.0,
            unit_cost=150.0,
            expiry_date=date.today() - timedelta(days=10),
        )
        item2 = InventoryItem(
            id=uuid.uuid4(),
            name="Dog Food 15kg",
            category="food",
            quantity=50.0,
            unit="bags",
            reorder_threshold=10.0,
            unit_cost=1200.0,
            expiry_date=date.today() + timedelta(days=120),
        )
        movement1 = InventoryMovement(
            id=uuid.uuid4(),
            item_id=item1.id,
            movement_type=MovementType.CHECK_IN,
            quantity=10.0,
            reference_type="purchase",
            created_at=datetime.now(UTC) - timedelta(days=5),
        )
        movement2 = InventoryMovement(
            id=uuid.uuid4(),
            item_id=item1.id,
            movement_type=MovementType.CHECK_OUT,
            quantity=5.0,
            reference_type="treatment",
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
        movement3 = InventoryMovement(
            id=uuid.uuid4(),
            item_id=item1.id,
            movement_type=MovementType.ADJUSTMENT,
            quantity=-2.0,
            reference_type="damage",
            created_at=datetime.now(UTC),
        )
        req = RequisitionOrder(
            id=uuid.uuid4(),
            item_id=item1.id,
            quantity=25.0,
            status=RequisitionStatus.PENDING,
        )

        mock_session.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[item1, item2]))
                )
            ),
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(
                        all=MagicMock(return_value=[movement1, movement2, movement3])
                    )
                )
            ),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[req])))),
        ]

        result = await service.get_inventory_analytics()
        assert result["report_type"] == "inventory"
        report = result["report"]
        assert report["title"] == "Inventory Consumption & Expiry Audit"
        sections = report["sections"]

        # 1. Health & Loss Audit
        health = sections["inventory_health_and_loss_audit"]
        assert health["total_catalog_items"] == 2
        assert "₹" in health["total_inventory_value"]
        assert "₹750.00" in health["expired_product_value"]
        assert "₹300.00" in health["inventory_loss_write_off_value"]
        assert "days" in health["stock_movement_speed"]

        # 2. Upcoming PO Requirements
        po_reqs = sections["upcoming_purchase_order_requirements"]["items"]
        assert len(po_reqs) == 1
        assert po_reqs[0]["name"] == "Rabies Vaccine"
        assert po_reqs[0]["suggested_order_qty"] == 35.0  # (20 * 2) - 5
        assert po_reqs[0]["estimated_cost"] == 5250.0

        # 3. Expired Product Values Audit
        expired = sections["expired_product_values_audit"]["items"]
        assert len(expired) == 1
        assert expired[0]["name"] == "Rabies Vaccine"
        assert expired[0]["loss_value"] == 750.0
        assert expired[0]["status"] == "EXPIRED"

        # 4. Stock Movement & Usage Summary
        movements_list = sections["stock_movement_and_usage_summary"]["records"]
        assert len(movements_list) == 3

        # 5. Pending Purchase Requisitions
        pending = sections["pending_purchase_requisition_orders"]["requisitions"]
        assert len(pending) == 1
        assert pending[0]["quantity"] == 25.0

    @pytest.mark.asyncio
    async def test_inventory_analytics_empty_data(self, service, mock_session):
        """2. Empty inventory data handles gracefully without division by zero or errors."""
        mock_session.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ]

        result = await service.get_inventory_analytics()
        assert result["report_type"] == "inventory"
        sections = result["report"]["sections"]
        health = sections["inventory_health_and_loss_audit"]
        assert health["total_catalog_items"] == 0
        assert health["total_inventory_value"] == "₹0.00"
        assert health["stock_movement_speed"] == "N/A"
        assert sections["upcoming_purchase_order_requirements"]["items"] == []
        assert sections["expired_product_values_audit"]["items"] == []
        assert sections["stock_movement_and_usage_summary"]["records"] == []
        assert sections["pending_purchase_requisition_orders"]["requisitions"] == []

    @pytest.mark.asyncio
    async def test_inventory_analytics_one_stock_movement(self, service, mock_session):
        """3. One stock movement verifies zip(timestamps, timestamps[1:], strict=False) safety."""
        import uuid
        from datetime import UTC, datetime

        from pawguard.modules.inventory.models import InventoryItem, InventoryMovement, MovementType

        item = InventoryItem(
            id=uuid.uuid4(),
            name="Bandage",
            category="medical",
            quantity=10.0,
            unit="rolls",
            reorder_threshold=5.0,
            unit_cost=20.0,
            expiry_date=None,
        )
        movement = InventoryMovement(
            id=uuid.uuid4(),
            item_id=item.id,
            movement_type=MovementType.CHECK_IN,
            quantity=10.0,
            reference_type="donation",
            created_at=datetime.now(UTC),
        )

        mock_session.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[item])))
            ),
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[movement])))
            ),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ]

        result = await service.get_inventory_analytics()
        health = result["report"]["sections"]["inventory_health_and_loss_audit"]
        assert health["stock_movement_speed"] == "N/A"
        assert "In: 10.0" in health["check_in_out_volume"]

    @pytest.mark.asyncio
    async def test_inventory_analytics_multiple_stock_movements(self, service, mock_session):
        """4. Multiple stock movements calculate interval speed correctly."""
        import uuid
        from datetime import UTC, datetime, timedelta

        from pawguard.modules.inventory.models import InventoryItem, InventoryMovement, MovementType

        item = InventoryItem(
            id=uuid.uuid4(),
            name="Syringes",
            category="medical",
            quantity=100.0,
            unit="pcs",
            reorder_threshold=50.0,
            unit_cost=5.0,
            expiry_date=None,
        )
        now = datetime.now(UTC)
        m1 = InventoryMovement(
            id=uuid.uuid4(),
            item_id=item.id,
            movement_type=MovementType.CHECK_IN,
            quantity=100.0,
            reference_type="po",
            created_at=now - timedelta(days=6),
        )
        m2 = InventoryMovement(
            id=uuid.uuid4(),
            item_id=item.id,
            movement_type=MovementType.CHECK_OUT,
            quantity=30.0,
            reference_type="treatment",
            created_at=now - timedelta(days=4),
        )
        m3 = InventoryMovement(
            id=uuid.uuid4(),
            item_id=item.id,
            movement_type=MovementType.CHECK_OUT,
            quantity=20.0,
            reference_type="treatment",
            created_at=now,
        )

        mock_session.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[item])))
            ),
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[m1, m2, m3])))
            ),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ]

        result = await service.get_inventory_analytics()
        health = result["report"]["sections"]["inventory_health_and_loss_audit"]
        assert "3.0 days" in health["stock_movement_speed"]

    @pytest.mark.asyncio
    async def test_inventory_analytics_zero_values(self, service, mock_session):
        """8. Zero values for unit costs and quantities calculate without exception."""
        import uuid

        from pawguard.modules.inventory.models import InventoryItem

        item = InventoryItem(
            id=uuid.uuid4(),
            name="Donated Blankets",
            category="shelter",
            quantity=0.0,
            unit="pcs",
            reorder_threshold=0.0,
            unit_cost=0.0,
            expiry_date=None,
        )

        mock_session.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[item])))
            ),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ]

        result = await service.get_inventory_analytics()
        health = result["report"]["sections"]["inventory_health_and_loss_audit"]
        assert health["total_inventory_value"] == "₹0.00"
        assert health["inventory_loss_rate_pct"] == "0.0%"

    @pytest.mark.asyncio
    async def test_inventory_analytics_api_endpoints_and_rbac(self):
        """9. RBAC & 10. Response schema validation across GET and POST analytics endpoints."""
        import json
        import uuid
        from datetime import UTC, datetime

        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from pawguard.core.security import AccessTokenClaims
        from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
        from pawguard.modules.auth.models import Permission, Role, User
        from pawguard.modules.reports.router import get_report_service
        from pawguard.modules.reports.router import router as reports_router
        from pawguard.modules.reports.schemas import InventoryAnalyticsResponse

        test_app = FastAPI()
        test_app.include_router(reports_router, prefix="/api/v1")

        mock_analytics_payload = {
            "report_type": "inventory",
            "report": {
                "title": "Inventory Consumption & Expiry Audit",
                "generated_at": "2026-09-09T05:00:00Z",
                "sections": {
                    "inventory_health_and_loss_audit": {
                        "total_catalog_items": 15,
                        "total_inventory_value": "₹45,000.00",
                        "expired_product_value": "₹1,200.00",
                        "inventory_loss_write_off_value": "₹500.00",
                        "inventory_loss_rate_pct": "1.1%",
                        "stock_movement_speed": "2.5 days",
                        "check_in_out_volume": "In: 100.0, Out: 40.0",
                        "upcoming_purchase_order_requirements_exposure": "₹15,000.00",
                    },
                    "upcoming_purchase_order_requirements": {
                        "items": [
                            {
                                "item_id": "item-1",
                                "name": "Surgical Gloves",
                                "category": "medical",
                                "current_stock": 2.0,
                                "reorder_threshold": 10.0,
                                "suggested_order_qty": 18.0,
                                "unit": "boxes",
                                "unit_cost": 250.0,
                                "estimated_cost": 4500.0,
                            }
                        ]
                    },
                    "expired_product_values_audit": {
                        "items": [
                            {
                                "item_id": "item-2",
                                "name": "Expired Saline",
                                "category": "medical",
                                "expired_qty": 4.0,
                                "expiry_date": "2026-08-01",
                                "unit_cost": 50.0,
                                "loss_value": 200.0,
                                "status": "EXPIRED",
                            }
                        ]
                    },
                    "stock_movement_and_usage_summary": {
                        "records": [
                            {
                                "reference_type": "treatment",
                                "check_in_qty": 0.0,
                                "check_out_qty": 30.0,
                                "adjustment_qty": 0.0,
                                "movement_count": 5,
                            }
                        ]
                    },
                    "pending_purchase_requisition_orders": {
                        "requisitions": [
                            {
                                "requisition_id": "req-1",
                                "item_id": "item-1",
                                "quantity": 20.0,
                                "status": "pending",
                            }
                        ]
                    },
                },
            },
        }

        mock_svc = AsyncMock()
        mock_svc.get_inventory_analytics.return_value = mock_analytics_payload

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
            code="reports:read",
            description="Read Reports",
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

        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(["reports:read", "reports:create"])
        mock_redis.set.return_value = True

        mock_db = AsyncMock()
        mock_db_result = MagicMock()
        mock_db_result.scalars.return_value.all.return_value = ["reports:read", "reports:create"]
        mock_db.execute.return_value = mock_db_result

        mock_current_user = CurrentUser(
            user=user,
            claims=claims,
            db=mock_db,
            redis=mock_redis,
        )

        for route in test_app.routes:
            if "/reports" in getattr(route, "path", ""):
                for dep in getattr(route, "dependencies", []):
                    test_app.dependency_overrides[dep.dependency] = lambda: mock_current_user

        test_app.dependency_overrides[get_current_user] = lambda: mock_current_user
        test_app.dependency_overrides[get_report_service] = lambda: mock_svc

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test GET /api/v1/reports/inventory/analytics
            res_get = await client.get("/api/v1/reports/inventory/analytics")
            assert res_get.status_code == 200
            data_get = res_get.json()
            assert data_get["success"] is True
            parsed_get = InventoryAnalyticsResponse(**data_get["data"])
            assert parsed_get.report_type == "inventory"
            assert parsed_get.report.title == "Inventory Consumption & Expiry Audit"
            assert (
                parsed_get.report.sections.inventory_health_and_loss_audit.total_inventory_value
                == "₹45,000.00"
            )

            # Test GET alias /api/v1/reports/analytics/inventory
            res_alias = await client.get("/api/v1/reports/analytics/inventory")
            assert res_alias.status_code == 200

            # Test POST /api/v1/reports/inventory/analytics
            res_post_inv = await client.post("/api/v1/reports/inventory/analytics", json={})
            assert res_post_inv.status_code == 200

            # Test POST /api/v1/reports/analytics
            res_post = await client.post(
                "/api/v1/reports/analytics",
                json={"report_type": "inventory", "filters": {"category": "medical"}},
            )
            assert res_post.status_code == 200
            data_post = res_post.json()
            assert data_post["success"] is True
            assert (
                data_post["data"]["report"]["sections"]["inventory_health_and_loss_audit"][
                    "upcoming_purchase_order_requirements_exposure"
                ]
                == "₹15,000.00"
            )


class TestMedicalAnalyticsEndpointsAndService:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        return ReportService(mock_session)

    @pytest.mark.asyncio
    async def test_medical_analytics_populated_data(self, service, mock_session):
        """1. Populated medical data across all 4 key sections."""
        import uuid
        from datetime import UTC, datetime, timedelta

        from pawguard.modules.medical.models import (
            MedicalTreatment,
            Prescription,
            VaccinationRecord,
        )

        dog1_id = uuid.uuid4()
        dog2_id = uuid.uuid4()
        now = datetime.now(UTC)

        # 2 vaccinations for 2 dogs
        v1 = VaccinationRecord(
            id=uuid.uuid4(),
            dog_id=dog1_id,
            administered_by=uuid.uuid4(),
            vaccine_name="Rabies",
            administered_at=now - timedelta(days=20),
            next_due_at=now + timedelta(days=340),
            lot_number="LOT-1",
        )
        v2 = VaccinationRecord(
            id=uuid.uuid4(),
            dog_id=dog2_id,
            administered_by=uuid.uuid4(),
            vaccine_name="DHPP",
            administered_at=now - timedelta(days=400),
            next_due_at=now - timedelta(days=35),  # Overdue
            lot_number="LOT-2",
        )

        # 2 treatments (1 surgery without post-op notes -> pending surgery, 1 routine therapy)
        t1 = MedicalTreatment(
            id=uuid.uuid4(),
            dog_id=dog1_id,
            vet_id=uuid.uuid4(),
            treatment_date=now - timedelta(days=2),
            treatment_type="Orthopedic Surgery",
            description="Left hind leg fracture stabilization",
            anesthesia_log="Isoflurane 2%",
            post_op_notes=None,  # Pending
        )
        t2 = MedicalTreatment(
            id=uuid.uuid4(),
            dog_id=dog2_id,
            vet_id=uuid.uuid4(),
            treatment_date=now - timedelta(days=10),
            treatment_type="Wound Dressing",
            description="Superficial scratch cleaned",
            anesthesia_log=None,
            post_op_notes="Healed cleanly",
        )

        # 1 prescription
        p1 = Prescription(
            id=uuid.uuid4(),
            dog_id=dog1_id,
            vet_id=uuid.uuid4(),
            drug_name="Amoxicillin",
            dosage="250mg",
            route="Oral",
            start_at=now - timedelta(days=5),
            end_at=now + timedelta(days=5),
            is_active=True,
        )

        mock_session.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[t1, t2])))
            ),
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[v1, v2])))
            ),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[p1])))),
            MagicMock(scalar=MagicMock(return_value=10)),  # 10 shelter dogs
            MagicMock(scalar=MagicMock(return_value=5000.0)),  # ₹5,000 vet expenses
        ]

        result = await service.get_medical_analytics()
        assert result["report_type"] == "medical"
        report = result["report"]
        assert report["title"] == "Medical Care & Immunization Compliance Report"
        sections = report["sections"]

        # 1. Vaccination Coverage Across Shelter Populations
        vax_sec = sections["vaccination_coverage_across_shelter_populations"]
        assert vax_sec["total_shelter_animals"] == 10
        assert vax_sec["vaccinated_animals"] == 2
        assert vax_sec["vaccination_coverage_rate_pct"] == "20.0%"
        assert len(vax_sec["vaccine_breakdown"]) == 2

        # 2. Pending Surgeries
        surg_sec = sections["pending_surgeries"]
        assert surg_sec["total_pending_surgeries"] == 1
        assert len(surg_sec["items"]) == 1
        assert surg_sec["items"][0]["treatment_type"] == "Orthopedic Surgery"
        assert surg_sec["items"][0]["treatment_id"] == str(t1.id)

        # 3. Follow-Up Exam Compliance
        followup_sec = sections["follow_up_exam_compliance"]
        assert followup_sec["total_follow_ups_due"] == 2
        assert followup_sec["on_track_follow_ups"] == 1
        assert followup_sec["overdue_follow_ups"] == 1
        assert followup_sec["compliance_rate_pct"] == "50.0%"

        # 4. Veterinary Expenditure Per Dog
        exp_sec = sections["veterinary_expenditure_per_dog"]
        assert exp_sec["total_veterinary_expenditure"] == "₹5000.00"
        assert exp_sec["total_shelter_dogs"] == 10
        assert exp_sec["dogs_with_veterinary_expenditure"] == 2
        assert exp_sec["average_expenditure_per_dog"] == "₹500.00"

    @pytest.mark.asyncio
    async def test_medical_analytics_empty_data(self, service, mock_session):
        """2. Empty medical data handles gracefully with zero defaults and no division by zero."""
        mock_session.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0.0)),
        ]

        result = await service.get_medical_analytics()
        assert result["report_type"] == "medical"
        sections = result["report"]["sections"]

        assert (
            sections["vaccination_coverage_across_shelter_populations"]["total_shelter_animals"]
            == 0
        )
        assert (
            sections["vaccination_coverage_across_shelter_populations"][
                "vaccination_coverage_rate_pct"
            ]
            == "0.0%"
        )
        assert sections["pending_surgeries"]["total_pending_surgeries"] == 0
        assert sections["pending_surgeries"]["items"] == []
        assert sections["follow_up_exam_compliance"]["total_follow_ups_due"] == 0
        assert sections["follow_up_exam_compliance"]["compliance_rate_pct"] == "100.0%"
        assert sections["veterinary_expenditure_per_dog"]["total_veterinary_expenditure"] == "₹0.00"
        assert sections["veterinary_expenditure_per_dog"]["average_expenditure_per_dog"] == "₹0.00"

    @pytest.mark.asyncio
    async def test_medical_analytics_vaccination_coverage_calculation(self, service, mock_session):
        """3. Vaccination coverage accurately counts distinct vaccinated dogs across multiple shots."""
        import uuid
        from datetime import UTC, datetime

        from pawguard.modules.medical.models import VaccinationRecord

        dog1_id = uuid.uuid4()
        now = datetime.now(UTC)

        # 2 vaccines given to the SAME dog
        v1 = VaccinationRecord(
            id=uuid.uuid4(),
            dog_id=dog1_id,
            administered_by=uuid.uuid4(),
            vaccine_name="Rabies",
            administered_at=now,
            next_due_at=None,
        )
        v2 = VaccinationRecord(
            id=uuid.uuid4(),
            dog_id=dog1_id,
            administered_by=uuid.uuid4(),
            vaccine_name="DHPP",
            administered_at=now,
            next_due_at=None,
        )

        mock_session.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[v1, v2])))
            ),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalar=MagicMock(return_value=4)),  # 4 shelter dogs total
            MagicMock(scalar=MagicMock(return_value=0.0)),
        ]

        result = await service.get_medical_analytics()
        vax = result["report"]["sections"]["vaccination_coverage_across_shelter_populations"]
        assert vax["vaccinated_animals"] == 1  # 1 distinct dog
        assert vax["total_shelter_animals"] == 4
        assert vax["vaccination_coverage_rate_pct"] == "25.0%"

    @pytest.mark.asyncio
    async def test_medical_analytics_pending_surgeries(self, service, mock_session):
        """4. Pending surgeries identifies only surgery treatments lacking post-op notes."""
        import uuid
        from datetime import UTC, datetime

        from pawguard.modules.medical.models import MedicalTreatment

        now = datetime.now(UTC)
        surg_pending = MedicalTreatment(
            id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            vet_id=uuid.uuid4(),
            treatment_date=now,
            treatment_type="Spay Surgery",
            description="Routine spay",
            post_op_notes=None,
        )
        surg_completed = MedicalTreatment(
            id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            vet_id=uuid.uuid4(),
            treatment_date=now,
            treatment_type="Neuter Surgery",
            description="Routine neuter",
            post_op_notes="Completed without complications",
        )
        consult = MedicalTreatment(
            id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            vet_id=uuid.uuid4(),
            treatment_date=now,
            treatment_type="Consultation",
            description="Ear inspection",
            post_op_notes=None,
        )

        mock_session.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(
                        all=MagicMock(return_value=[surg_pending, surg_completed, consult])
                    )
                )
            ),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalar=MagicMock(return_value=5)),
            MagicMock(scalar=MagicMock(return_value=0.0)),
        ]

        result = await service.get_medical_analytics()
        pending = result["report"]["sections"]["pending_surgeries"]
        assert pending["total_pending_surgeries"] == 1
        assert pending["items"][0]["treatment_id"] == str(surg_pending.id)

    @pytest.mark.asyncio
    async def test_medical_analytics_veterinary_expenditure_per_dog(self, service, mock_session):
        """6. Veterinary expenditure per dog calculates correctly."""
        mock_session.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalar=MagicMock(return_value=8)),
            MagicMock(scalar=MagicMock(return_value=12000.0)),
        ]

        result = await service.get_medical_analytics()
        exp = result["report"]["sections"]["veterinary_expenditure_per_dog"]
        assert exp["total_veterinary_expenditure"] == "₹12000.00"
        assert exp["total_shelter_dogs"] == 8
        assert exp["average_expenditure_per_dog"] == "₹1500.00"

    @pytest.mark.asyncio
    async def test_medical_analytics_api_endpoints_and_rbac(self):
        """8. RBAC authorization & 9. Response schema validation for medical analytics."""
        import json
        import uuid
        from datetime import UTC, datetime

        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from pawguard.core.security import AccessTokenClaims
        from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
        from pawguard.modules.auth.models import Permission, Role, User
        from pawguard.modules.reports.router import get_report_service
        from pawguard.modules.reports.router import router as reports_router
        from pawguard.modules.reports.schemas import MedicalAnalyticsResponse

        test_app = FastAPI()
        test_app.include_router(reports_router, prefix="/api/v1")

        mock_medical_payload = {
            "report_type": "medical",
            "report": {
                "title": "Medical Care & Immunization Compliance Report",
                "generated_at": "2026-09-09T05:30:00Z",
                "sections": {
                    "vaccination_coverage_across_shelter_populations": {
                        "total_shelter_animals": 20,
                        "vaccinated_animals": 16,
                        "vaccination_coverage_rate_pct": "80.0%",
                        "vaccine_breakdown": [
                            {
                                "vaccine_name": "Rabies",
                                "doses_administered": 16,
                                "dogs_vaccinated": 16,
                            }
                        ],
                    },
                    "pending_surgeries": {
                        "total_pending_surgeries": 2,
                        "items": [
                            {
                                "treatment_id": "treat-1",
                                "dog_id": "dog-1",
                                "vet_id": "vet-1",
                                "treatment_type": "Orthopedic Surgery",
                                "treatment_date": "2026-09-08",
                                "notes": "Awaiting surgeon",
                            }
                        ],
                    },
                    "follow_up_exam_compliance": {
                        "total_follow_ups_due": 10,
                        "completed_follow_ups": 8,
                        "on_track_follow_ups": 8,
                        "overdue_follow_ups": 2,
                        "no_follow_up_scheduled": 0,
                        "compliance_rate_pct": "80.0%",
                    },
                    "veterinary_expenditure_per_dog": {
                        "total_veterinary_expenditure": "₹24,000.00",
                        "dogs_with_veterinary_expenditure": 16,
                        "total_shelter_dogs": 20,
                        "average_expenditure_per_dog": "₹1,200.00",
                    },
                },
            },
        }

        mock_svc = AsyncMock()
        mock_svc.get_medical_analytics.return_value = mock_medical_payload

        now = datetime.now(UTC)
        role = Role(
            id=uuid.uuid4(),
            name="veterinarian",
            description="Veterinarian",
            is_system=True,
            created_at=now,
            updated_at=now,
        )
        perm = Permission(
            id=uuid.uuid4(),
            code="reports:read",
            description="Read Reports",
            created_at=now,
            updated_at=now,
        )
        role.permissions = [perm]
        user = User(
            id=uuid.uuid4(),
            email="vet@pawguard.com",
            hashed_password="hash",
            full_name="Staff Veterinarian",
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
            roles=["veterinarian"],
            jti="jti",
            expires_at=now,
        )

        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(["reports:read", "reports:create"])
        mock_redis.set.return_value = True

        mock_db = AsyncMock()
        mock_db_result = MagicMock()
        mock_db_result.scalars.return_value.all.return_value = ["reports:read", "reports:create"]
        mock_db.execute.return_value = mock_db_result

        mock_current_user = CurrentUser(
            user=user,
            claims=claims,
            db=mock_db,
            redis=mock_redis,
        )

        for route in test_app.routes:
            if "/reports" in getattr(route, "path", ""):
                for dep in getattr(route, "dependencies", []):
                    test_app.dependency_overrides[dep.dependency] = lambda: mock_current_user

        test_app.dependency_overrides[get_current_user] = lambda: mock_current_user
        test_app.dependency_overrides[get_report_service] = lambda: mock_svc

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test GET /api/v1/reports/medical/analytics
            res_get = await client.get("/api/v1/reports/medical/analytics")
            assert res_get.status_code == 200
            data_get = res_get.json()
            assert data_get["success"] is True
            parsed_get = MedicalAnalyticsResponse(**data_get["data"])
            assert parsed_get.report_type == "medical"
            assert parsed_get.report.title == "Medical Care & Immunization Compliance Report"
            assert (
                parsed_get.report.sections.vaccination_coverage_across_shelter_populations.vaccination_coverage_rate_pct
                == "80.0%"
            )

            # Test GET alias /api/v1/reports/analytics/medical
            res_alias = await client.get("/api/v1/reports/analytics/medical")
            assert res_alias.status_code == 200

            # Test POST /api/v1/reports/medical/analytics
            res_post_med = await client.post("/api/v1/reports/medical/analytics", json={})
            assert res_post_med.status_code == 200

            # Test POST /api/v1/reports/analytics with report_type=medical
            res_post = await client.post(
                "/api/v1/reports/analytics",
                json={"report_type": "medical"},
            )
            assert res_post.status_code == 200
            data_post = res_post.json()
            assert data_post["success"] is True
            assert (
                data_post["data"]["report"]["sections"]["pending_surgeries"][
                    "total_pending_surgeries"
                ]
                == 2
            )
