import os
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pii import mask_report_data
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.donation.models import Donation
from pawguard.modules.finance.models import FinancialTransaction
from pawguard.modules.foster.models import FosterPlacement
from pawguard.modules.inventory.models import InventoryItem
from pawguard.modules.medical.models import MedicalTreatment
from pawguard.modules.reports.renderers import (
    ensure_reports_dir,
    generate_csv,
    generate_excel,
    generate_pdf,
    report_filename,
)
from pawguard.modules.reports.schemas import ReportFormat, ReportType
from pawguard.modules.rescue.models import RescueDispatch, RescueRequest
from pawguard.modules.volunteer.models import VolunteerProfile


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def generate_report(
        self,
        report_type: ReportType,
        fmt: ReportFormat,
        period_start: date | None = None,
        period_end: date | None = None,
        filters: dict | None = None,
    ) -> dict:
        raw_data = await self._collect_data(
            report_type, period_start, period_end, filters
        )
        title = raw_data["title"]
        headers = raw_data["headers"]
        rows = raw_data["rows"]
        subtitle = raw_data.get("subtitle")

        if fmt == ReportFormat.CSV:
            content = generate_csv(headers, rows)
            ext = "csv"
            content_type = "text/csv"
        elif fmt == ReportFormat.EXCEL:
            content = generate_excel(
                report_type.value, headers, rows, title=title
            )
            ext = "xlsx"
            content_type = (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
        else:
            content = generate_pdf(title, headers, rows, subtitle=subtitle)
            ext = "pdf"
            content_type = "application/pdf"

        fname = report_filename(report_type.value, ext)
        reports_dir = ensure_reports_dir()
        filepath = os.path.join(reports_dir, fname)
        with open(filepath, "wb") as f:  # noqa: ASYNC230
            f.write(content)

        return {
            "report_type": report_type.value,
            "format": fmt.value,
            "filename": fname,
            "content_type": content_type,
            "size_bytes": len(content),
            "download_url": f"/api/v1/reports/download/{fname}",
        }

    async def _collect_data(
        self,
        report_type: ReportType,
        period_start: date | None,
        period_end: date | None,
        filters: dict | None,
    ) -> dict:
        match report_type:
            case ReportType.DONATION:
                return await self._donation_report(
                    period_start, period_end, filters
                )
            case ReportType.ADOPTION:
                return await self._adoption_report(
                    period_start, period_end, filters
                )
            case ReportType.MEDICAL:
                return await self._medical_report(
                    period_start, period_end, filters
                )
            case ReportType.INVENTORY:
                return await self._inventory_report(filters)
            case ReportType.RESCUE:
                return await self._rescue_report(
                    period_start, period_end, filters
                )
            case ReportType.FINANCE:
                return await self._finance_report(
                    period_start, period_end, filters
                )
            case ReportType.STAFF_PERFORMANCE:
                return await self._staff_performance_report(
                    period_start, period_end, filters
                )
            case ReportType.ANIMAL_POPULATION:
                return await self._animal_population_report(filters)
            case ReportType.FOSTER:
                return await self._foster_report(
                    period_start, period_end, filters
                )
            case ReportType.VOLUNTEER:
                return await self._volunteer_report(
                    period_start, period_end, filters
                )
            case _:
                return {"title": "Report", "headers": [], "rows": []}

    async def _donation_report(
        self, start: date | None, end: date | None, filters: dict | None
    ) -> dict:
        stmt = select(Donation)
        if start:
            stmt = stmt.where(Donation.created_at >= start)
        if end:
            stmt = stmt.where(Donation.created_at <= end)
        if filters and "status" in filters:
            stmt = stmt.where(Donation.status == filters["status"])
        results = (await self._session.execute(stmt)).scalars().all()
        return {
            "title": "Donation Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": [
                "ID", "Donor", "Amount", "Currency", "Type", "Status", "Date"
            ],
            "rows": [
                [str(d.id), str(d.donor_id), float(d.amount), d.currency,
                 d.donation_type, d.status, d.created_at.date()]
                for d in results
            ],
        }

    async def _adoption_report(
        self, start: date | None, end: date | None, filters: dict | None
    ) -> dict:
        stmt = select(AdoptionApplication)
        if start:
            stmt = stmt.where(AdoptionApplication.created_at >= start)
        if end:
            stmt = stmt.where(AdoptionApplication.created_at <= end)
        if filters and "status" in filters:
            stmt = stmt.where(
                AdoptionApplication.status == filters["status"]
            )
        results = (await self._session.execute(stmt)).scalars().all()
        headers = [
            "ID", "Dog ID", "Adopter ID", "Status",
            "Submitted At", "Completed At",
        ]
        rows = [
            [str(a.id), str(a.dog_id), str(a.adopter_id), a.status,
             a.created_at.date(),
             a.completed_at.date() if a.completed_at else ""]
            for a in results
        ]
        rows = mask_report_data(rows, headers, {"Adopter Name", "Adopter Email", "Adopter Phone"})
        return {
            "title": "Adoption Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": headers,
            "rows": rows,
        }

    async def _medical_report(
        self, start: date | None, end: date | None, filters: dict | None
    ) -> dict:
        stmt = select(MedicalTreatment)
        if start:
            stmt = stmt.where(MedicalTreatment.treatment_date >= start)
        if end:
            stmt = stmt.where(MedicalTreatment.treatment_date <= end)
        results = (await self._session.execute(stmt)).scalars().all()
        return {
            "title": "Medical Treatment Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": ["ID", "Dog ID", "Vet ID", "Treatment Type", "Date"],
            "rows": [
                [str(m.id), str(m.dog_id), str(m.vet_id), m.treatment_type,
                 m.treatment_date.date()
                 if hasattr(m.treatment_date, "date")
                 else m.treatment_date]
                for m in results
            ],
        }

    async def _inventory_report(
        self, filters: dict | None
    ) -> dict:
        stmt = select(InventoryItem)
        if filters and "category" in filters:
            stmt = stmt.where(
                InventoryItem.category == filters["category"]
            )
        results = (await self._session.execute(stmt)).scalars().all()
        return {
            "title": "Inventory Report",
            "headers": [
                "ID", "Name", "Category", "Quantity",
                "Unit", "Reorder Threshold",
            ],
            "rows": [
                [str(i.id), i.name, i.category, float(i.quantity),
                 i.unit, float(i.reorder_threshold)]
                for i in results
            ],
        }

    async def _rescue_report(
        self, start: date | None, end: date | None, filters: dict | None
    ) -> dict:
        stmt = select(RescueRequest)
        if start:
            stmt = stmt.where(RescueRequest.created_at >= start)
        if end:
            stmt = stmt.where(RescueRequest.created_at <= end)
        if filters and "status" in filters:
            stmt = stmt.where(RescueRequest.status == filters["status"])
        results = (await self._session.execute(stmt)).scalars().all()
        headers = [
            "ID", "Ticket", "Status", "Reporter",
            "Location", "Animal Count", "Created",
        ]
        rows = [
            [str(r.id), r.ticket_number, r.status, r.reporter_name,
             r.location_address, r.animal_count, r.created_at.date()]
            for r in results
        ]
        rows = mask_report_data(rows, headers, {"Reporter"})
        return {
            "title": "Rescue Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": headers,
            "rows": rows,
        }

    async def _finance_report(
        self, start: date | None, end: date | None, filters: dict | None
    ) -> dict:
        stmt = select(FinancialTransaction).where(
            FinancialTransaction.deleted_at.is_(None),
        )
        if start:
            stmt = stmt.where(
                FinancialTransaction.transaction_date >= start
            )
        if end:
            stmt = stmt.where(
                FinancialTransaction.transaction_date <= end
            )
        if filters and "type" in filters:
            stmt = stmt.where(
                FinancialTransaction.transaction_type == filters["type"]
            )
        if filters and "status" in filters:
            stmt = stmt.where(
                FinancialTransaction.status == filters["status"]
            )
        results = (await self._session.execute(stmt)).scalars().all()
        return {
            "title": "Finance Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": [
                "ID", "Number", "Type", "Amount",
                "Currency", "Status", "Date",
            ],
            "rows": [
                [str(t.id), t.transaction_number, t.transaction_type,
                 float(t.amount), t.currency, t.status, t.transaction_date]
                for t in results
            ],
        }

    @staticmethod
    def _months_in_range(start: date | None, end: date | None) -> int:
        if not start or not end:
            return 1
        return max(1, (end.year - start.year) * 12 + end.month - start.month + 1)

    async def _staff_performance_report(
        self, start: date | None, end: date | None, filters: dict | None
    ) -> dict:
        adoption_stmt = select(func.count(AdoptionApplication.id)).where(
            AdoptionApplication.status == AdoptionStatus.COMPLETED
        )
        if start:
            adoption_stmt = adoption_stmt.where(AdoptionApplication.created_at >= start)
        if end:
            adoption_stmt = adoption_stmt.where(AdoptionApplication.created_at <= end)
        total_adoptions = (await self._session.execute(adoption_stmt)).scalar() or 0

        months = self._months_in_range(start, end)
        adoption_velocity = total_adoptions / months

        active_foster_stmt = select(func.count(FosterPlacement.id)).where(
            FosterPlacement.is_active.is_(True)
        )
        active_foster = (await self._session.execute(active_foster_stmt)).scalar() or 0

        total_placements_stmt = select(func.count(FosterPlacement.id))
        total_placements = (await self._session.execute(total_placements_stmt)).scalar() or 0
        returned_placements_stmt = select(func.count(FosterPlacement.id)).where(
            FosterPlacement.returned_at.isnot(None)
        )
        returned_placements = (await self._session.execute(returned_placements_stmt)).scalar() or 0
        foster_efficiency = (
            (returned_placements / total_placements * 100) if total_placements else 0.0
        )

        rescue_stmt = select(func.count(RescueRequest.id))
        if start:
            rescue_stmt = rescue_stmt.where(RescueRequest.created_at >= start)
        if end:
            rescue_stmt = rescue_stmt.where(RescueRequest.created_at <= end)
        rescue_count = (await self._session.execute(rescue_stmt)).scalar() or 0

        avg_response_stmt = select(
            func.avg(
                func.extract(
                    "epoch",
                    RescueDispatch.dispatched_at - RescueRequest.created_at,
                ) / 3600.0
            )
        ).select_from(RescueDispatch).join(
            RescueRequest, RescueDispatch.rescue_request_id == RescueRequest.id
        )
        if start:
            avg_response_stmt = avg_response_stmt.where(RescueRequest.created_at >= start)
        if end:
            avg_response_stmt = avg_response_stmt.where(RescueRequest.created_at <= end)
        avg_response_time = (await self._session.execute(avg_response_stmt)).scalar()
        avg_response_time = round(avg_response_time, 1) if avg_response_time is not None else None

        medical_stmt = select(func.count(MedicalTreatment.id))
        if start:
            medical_stmt = medical_stmt.where(MedicalTreatment.treatment_date >= start)
        if end:
            medical_stmt = medical_stmt.where(MedicalTreatment.treatment_date <= end)
        medical_count = (await self._session.execute(medical_stmt)).scalar() or 0

        dogs_in_care_stmt = select(func.count(DogProfile.id)).where(
            DogProfile.status != DogStatus.ADOPTED
        )
        dogs_in_care = (await self._session.execute(dogs_in_care_stmt)).scalar() or 0

        avg_los_stmt = select(
            func.avg(
                func.extract("epoch", func.now() - DogProfile.created_at) / 86400.0
            )
        ).where(DogProfile.status != DogStatus.ADOPTED)
        avg_los = (await self._session.execute(avg_los_stmt)).scalar()
        avg_los = round(avg_los, 1) if avg_los is not None else None

        volunteer_stmt = select(func.count(VolunteerProfile.id)).where(
            VolunteerProfile.status == "active"
        )
        volunteer_count = (await self._session.execute(volunteer_stmt)).scalar() or 0

        return {
            "title": "Staff Performance Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": ["Metric", "Value"],
            "rows": [
                ["Total Adoptions", str(total_adoptions)],
                ["Adoption Velocity", f"{adoption_velocity:.1f} / month"],
                ["Active Foster Placements", str(active_foster)],
                ["Foster Efficiency Rate", f"{foster_efficiency:.1f}%"],
                ["Rescue Response Count", str(rescue_count)],
                [
                    "Avg Rescue Response Time",
                    f"{avg_response_time}h" if avg_response_time is not None else "N/A",
                ],
                ["Medical Treatments This Period", str(medical_count)],
                ["Total Dogs in Care", str(dogs_in_care)],
                [
                    "Avg Length of Stay",
                    f"{avg_los} days" if avg_los is not None else "N/A",
                ],
                ["Volunteer Hours", str(volunteer_count)],
            ],
        }

    async def _animal_population_report(
        self, filters: dict | None
    ) -> dict:
        stmt = select(DogProfile)
        if filters and "status" in filters:
            stmt = stmt.where(DogProfile.status == filters["status"])
        if filters and "breed" in filters:
            stmt = stmt.where(DogProfile.breed == filters["breed"])
        results = (await self._session.execute(stmt)).scalars().all()
        return {
            "title": "Animal Population Report",
            "headers": [
                "ID", "Name", "Breed", "Gender",
                "Status", "Age", "Weight",
            ],
            "rows": [
                [str(d.id), d.name, d.breed, d.gender, d.status,
                 d.estimated_age or "",
                 float(d.weight) if d.weight else ""]
                for d in results
            ],
        }

    async def _foster_report(
        self, start: date | None, end: date | None, filters: dict | None
    ) -> dict:
        stmt = select(FosterPlacement)
        if start:
            stmt = stmt.where(FosterPlacement.placed_at >= start)
        if end:
            stmt = stmt.where(FosterPlacement.placed_at <= end)
        results = (await self._session.execute(stmt)).scalars().all()
        return {
            "title": "Foster Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": [
                "ID", "Foster ID", "Dog ID", "Placed At",
                "Returned At", "Active",
            ],
            "rows": [
                [str(f.id), str(f.foster_id), str(f.dog_id),
                 f.placed_at.date()
                 if hasattr(f.placed_at, "date") else f.placed_at,
                 f.returned_at.date() if f.returned_at else "",
                 "Yes" if f.is_active else "No"]
                for f in results
            ],
        }

    async def _volunteer_report(
        self, start: date | None, end: date | None, filters: dict | None
    ) -> dict:
        stmt = select(VolunteerProfile)
        if filters and "status" in filters:
            stmt = stmt.where(
                VolunteerProfile.status == filters["status"]
            )
        results = (await self._session.execute(stmt)).scalars().all()
        return {
            "title": "Volunteer Report",
            "headers": ["ID", "User ID", "Status", "Skills", "Available"],
            "rows": [
                [str(v.id), str(v.user_id), v.status,
                 v.skills or "", "Yes" if v.is_available else "No"]
                for v in results
            ],
        }
