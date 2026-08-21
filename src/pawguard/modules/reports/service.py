import asyncio
import os
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pii import mask_report_data
from pawguard.modules.adoption.models import (
    AdoptionApplication,
    AdoptionScore,
    AdoptionStatus,
)
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.donation.models import (
    Donation,
    DonationCampaign,
    DonationStatus,
)
from pawguard.modules.finance.models import (
    ChartOfAccounts,
    FinancialTransaction,
    GeneralLedgerEntry,
    TransactionStatus,
    TransactionType,
)
from pawguard.modules.foster.models import FosterPlacement
from pawguard.modules.inventory.models import (
    InventoryItem,
    InventoryMovement,
    MovementType,
    RequisitionOrder,
    RequisitionStatus,
)
from pawguard.modules.medical.models import (
    MedicalTreatment,
    Prescription,
    VaccinationRecord,
)
from pawguard.modules.reports.renderers import (
    ensure_reports_dir,
    generate_csv,
    generate_excel,
    generate_pdf,
    report_filename,
)
from pawguard.modules.reports.schemas import ReportFormat, ReportType
from pawguard.modules.rescue.models import RescueDispatch, RescueRequest, RescueStatus
from pawguard.modules.shelter.models import (
    FacilityTransfer,
    Kennel,
    ShelterFacility,
    ShelterSection,
    TransferStatus,
)
from pawguard.modules.volunteer.models import VolunteerProfile, VolunteerStatus


def _coerce_utc(value):
    if value is None or not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_overdue(next_due_at) -> bool:
    value = _coerce_utc(next_due_at)
    if value is None:
        return False
    try:
        return value < datetime.now(UTC)
    except TypeError:
        return False


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def generate_report(
        self,
        report_type: ReportType,
        fmt: ReportFormat,
        period_start: date | None = None,
        period_end: date | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw_data = await self._collect_data(report_type, period_start, period_end, filters)
        title = raw_data["title"]
        headers = raw_data["headers"]
        rows = raw_data["rows"]
        subtitle = raw_data.get("subtitle")
        sections = raw_data.get("sections") or None

        if fmt == ReportFormat.CSV:
            content = await asyncio.to_thread(generate_csv, headers, rows, sections=sections)
            ext = "csv"
            content_type = "text/csv"
        elif fmt == ReportFormat.EXCEL:
            content = await asyncio.to_thread(
                generate_excel, report_type.value, headers, rows, title=title, sections=sections
            )
            ext = "xlsx"
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            content = await asyncio.to_thread(
                generate_pdf, title, headers, rows, subtitle=subtitle, sections=sections
            )
            ext = "pdf"
            content_type = "application/pdf"

        fname = report_filename(report_type.value, ext)
        reports_dir = ensure_reports_dir()
        filepath = os.path.join(reports_dir, fname)

        def _write_file(path: str, data: bytes) -> None:
            with open(path, "wb") as f:
                f.write(data)

        await asyncio.to_thread(_write_file, filepath, content)

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
        filters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        match report_type:
            case ReportType.DONATION:
                return await self._donation_report(period_start, period_end, filters)
            case ReportType.ADOPTION:
                return await self._adoption_report(period_start, period_end, filters)
            case ReportType.MEDICAL:
                return await self._medical_report(period_start, period_end, filters)
            case ReportType.INVENTORY:
                return await self._inventory_report(filters)
            case ReportType.RESCUE:
                return await self._rescue_report(period_start, period_end, filters)
            case ReportType.FINANCE:
                return await self._finance_report(period_start, period_end, filters)
            case ReportType.STAFF_PERFORMANCE:
                return await self._staff_performance_report(period_start, period_end, filters)
            case ReportType.ANIMAL_POPULATION:
                return await self._animal_population_report(filters)
            case ReportType.FOSTER:
                return await self._foster_report(period_start, period_end, filters)
            case ReportType.VOLUNTEER:
                return await self._volunteer_report(period_start, period_end, filters)
            case ReportType.SHELTER:
                return await self._shelter_report(period_start, period_end, filters)
            case _:
                return {"title": "Report", "headers": [], "rows": []}

    async def _donation_report(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        stmt = select(Donation)
        if start:
            stmt = stmt.where(Donation.created_at >= start)
        if end:
            stmt = stmt.where(Donation.created_at <= end)
        if filters and "status" in filters:
            stmt = stmt.where(Donation.status == filters["status"])
        results = (await self._session.execute(stmt)).scalars().all()
        headers = ["ID", "Donor", "Amount", "Currency", "Type", "Status", "Campaign", "Date"]
        rows = [
            [
                str(d.id),
                str(d.donor_id),
                float(d.amount),
                d.currency,
                d.donation_type,
                d.status,
                d.campaign.name if d.campaign else "",
                d.created_at.date(),
            ]
            for d in results
        ]

        # Campaign progress metrics (PRR 4.1): how each drive is performing
        # toward its fundraising goal. Use single aggregated query instead of N+1.
        campaign_stmt = (
            select(
                DonationCampaign.id,
                DonationCampaign.name,
                DonationCampaign.campaign_type,
                DonationCampaign.status,
                DonationCampaign.target_amount,
                func.coalesce(func.sum(Donation.amount), 0).label("raised"),
            )
            .select_from(DonationCampaign)
            .outerjoin(
                Donation,
                (Donation.campaign_id == DonationCampaign.id) & (Donation.status == "success"),
            )
            .where(DonationCampaign.deleted_at.is_(None))
            .group_by(
                DonationCampaign.id,
                DonationCampaign.name,
                DonationCampaign.campaign_type,
                DonationCampaign.status,
                DonationCampaign.target_amount,
            )
        )
        campaign_rows_raw = (await self._session.execute(campaign_stmt)).all()
        campaign_rows = []
        for row in campaign_rows_raw:
            c_id, name, c_type, status, target, raised = row
            raised = float(raised)
            pct = (raised / float(target) * 100.0) if float(target) else 0.0
            campaign_rows.append(
                [
                    name,
                    c_type,
                    status,
                    f"{float(target):.2f}",
                    f"{raised:.2f}",
                    f"{min(pct, 100.0):.1f}%",
                ]
            )

        return {
            "title": "Donation Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": headers,
            "rows": rows,
            "sections": [
                {
                    "title": "Campaign Progress",
                    "headers": [
                        "Campaign",
                        "Type",
                        "Status",
                        "Target",
                        "Raised",
                        "Progress",
                    ],
                    "rows": campaign_rows,
                }
            ]
            if campaign_rows
            else [],
        }

    async def _adoption_report(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        # Parallelise independent DB reads.
        applications_task = asyncio.ensure_future(self._fetch_adoption_apps(start, end, filters))
        scores_task = asyncio.ensure_future(self._fetch_adoption_scores(start, end))
        results, scores = await asyncio.gather(applications_task, scores_task)

        headers = [
            "ID",
            "Dog ID",
            "Adopter ID",
            "Status",
            "Submitted At",
            "Completed At",
        ]
        rows = [
            [
                str(a.id),
                str(a.dog_id),
                str(a.adopter_id),
                a.status,
                a.created_at.date(),
                a.completed_at.date() if a.completed_at else "",
            ]
            for a in results
        ]
        rows = mask_report_data(rows, headers, {"Adopter Name", "Adopter Email", "Adopter Phone"})

        # Vetting & pipeline analytics (PRR 4.1 Adoption Velocity Index).
        total = len(results)
        completed = sum(1 for a in results if a.status == AdoptionStatus.COMPLETED)
        conversion_rate = (completed / total * 100.0) if total else 0.0

        score_list = list(scores)
        avg_score = (
            sum(float(s.overall_score) for s in score_list) / len(score_list)
            if score_list
            else None
        )
        recommendation_counts: dict[str, int] = {}
        for s in score_list:
            recommendation_counts[s.recommendation] = (
                recommendation_counts.get(s.recommendation, 0) + 1
            )

        completed_apps = [
            a
            for a in results
            if a.status == AdoptionStatus.COMPLETED and a.completed_at is not None
        ]
        completion_days = [
            (a.completed_at - a.created_at).total_seconds() / 86400.0 for a in completed_apps
        ]
        avg_days = sum(completion_days) / len(completion_days) if completion_days else None

        months = self._months_in_range(start, end)
        velocity = (completed / months) if months else 0.0

        rejection_counts: dict[str, int] = {}
        for a in results:
            if a.status != AdoptionStatus.REJECTED:
                continue
            if a.home_inspection_notes:
                stage = "home_check"
            elif a.vetting_officer_notes:
                stage = "vetting"
            else:
                stage = "submitted"
            rejection_counts[stage] = rejection_counts.get(stage, 0) + 1

        sections = [
            {
                "title": "Vetting & Pipeline",
                "headers": ["Metric", "Value"],
                "rows": [
                    ["Total Applications", str(total)],
                    ["Completed", str(completed)],
                    ["Conversion Rate", f"{conversion_rate:.1f}%"],
                    ["Avg Interview Score", f"{avg_score:.1f}" if avg_score is not None else "N/A"],
                    ["Avg Days to Complete", f"{avg_days:.1f}" if avg_days is not None else "N/A"],
                    ["Adoption Velocity Index", f"{velocity:.2f} adoptions / month"],
                ],
            }
        ]
        if recommendation_counts:
            sections.append(
                {
                    "title": "Interview Recommendation Distribution",
                    "headers": ["Recommendation", "Count"],
                    "rows": [
                        [recommendation, str(count)]
                        for recommendation, count in sorted(
                            recommendation_counts.items(), key=lambda item: item[1], reverse=True
                        )
                    ],
                }
            )
        if rejection_counts:
            sections.append(
                {
                    "title": "Rejection Distribution",
                    "headers": ["Rejected Stage", "Count"],
                    "rows": [
                        [stage, str(count)] for stage, count in sorted(rejection_counts.items())
                    ],
                }
            )

        return {
            "title": "Adoption Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": headers,
            "rows": rows,
            "sections": sections,
        }

    async def _fetch_adoption_apps(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ):
        stmt = select(AdoptionApplication)
        if start:
            stmt = stmt.where(AdoptionApplication.created_at >= start)
        if end:
            stmt = stmt.where(AdoptionApplication.created_at <= end)
        if filters and "status" in filters:
            stmt = stmt.where(AdoptionApplication.status == filters["status"])
        return (await self._session.execute(stmt)).scalars().all()

    async def _fetch_adoption_scores(self, start: date | None, end: date | None):
        stmt = select(AdoptionScore)
        if start:
            stmt = stmt.where(AdoptionScore.scored_at >= start)
        if end:
            stmt = stmt.where(AdoptionScore.scored_at <= end)
        return (await self._session.execute(stmt)).scalars().all()

    async def _medical_report(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        # Parallelise independent DB reads.
        treatments_task = asyncio.ensure_future(self._fetch_medical_treatments(start, end))
        vaccinations_task = asyncio.ensure_future(self._fetch_vaccinations(start, end))
        prescriptions_task = asyncio.ensure_future(self._fetch_prescriptions(start, end))
        total_dogs_task = asyncio.ensure_future(self._fetch_total_dogs())
        treatments, vaccinations, prescriptions, total_dogs = await asyncio.gather(
            treatments_task,
            vaccinations_task,
            prescriptions_task,
            total_dogs_task,
        )
        total_dogs = int(total_dogs)

        # Vaccination coverage (PRR 4.1 Medical Care & Immunization Compliance).
        vaccine_counts: dict[str, int] = {}
        vaccine_dogs: dict[str, set[str]] = {}
        vaccinated_dog_ids: set[str] = set()
        for v in vaccinations:
            vaccine_counts[v.vaccine_name] = vaccine_counts.get(v.vaccine_name, 0) + 1
            dog_key = str(v.dog_id)
            vaccine_dogs.setdefault(v.vaccine_name, set()).add(dog_key)
            vaccinated_dog_ids.add(dog_key)
        coverage_pct = (len(vaccinated_dog_ids) / total_dogs * 100.0) if total_dogs else 0.0

        # Follow-up / compliance (PRR 4.1): vaccinations whose next_due_at is
        # past their due date are overdue.
        overdue = 0
        on_track = 0
        no_followup = 0
        for v in vaccinations:
            if v.next_due_at is None:
                no_followup += 1
            elif _is_overdue(v.next_due_at):
                overdue += 1
            else:
                on_track += 1

        prescription_counts: dict[str, int] = {}
        active_prescriptions = 0
        for p in prescriptions:
            prescription_counts[p.drug_name] = prescription_counts.get(p.drug_name, 0) + 1
            if p.is_active:
                active_prescriptions += 1

        # Pending surgery backlog: MedicalTreatment has no completed flag, so a
        # surgery-type treatment lacking post-op notes is treated as pending.
        pending_surgeries = [
            t
            for t in treatments
            if t.treatment_type and "surg" in t.treatment_type.lower() and not t.post_op_notes
        ]

        sections = []
        if vaccinations:
            sections.append(
                {
                    "title": "Vaccination Coverage",
                    "headers": ["Vaccine Name", "Doses Administered", "Dogs Vaccinated"],
                    "rows": [
                        [name, str(count), str(len(vaccine_dogs.get(name, set())))]
                        for name, count in sorted(
                            vaccine_counts.items(), key=lambda item: item[1], reverse=True
                        )
                    ],
                }
            )
        sections.append(
            {
                "title": "Vaccination & Follow-up Compliance",
                "headers": ["Metric", "Value"],
                "rows": [
                    ["Total Dogs", str(total_dogs)],
                    ["Dogs Vaccinated", str(len(vaccinated_dog_ids))],
                    ["Vaccination Coverage", f"{coverage_pct:.1f}%"],
                    ["Follow-ups Overdue", str(overdue)],
                    ["Follow-ups On Track", str(on_track)],
                    ["No Follow-up Scheduled", str(no_followup)],
                ],
            }
        )
        if prescriptions:
            sections.append(
                {
                    "title": "Prescription Summary",
                    "headers": ["Drug Name", "Total", "Active"],
                    "rows": [
                        [
                            name,
                            str(count),
                            str(
                                sum(1 for p in prescriptions if p.drug_name == name and p.is_active)
                            ),
                        ]
                        for name, count in sorted(
                            prescription_counts.items(), key=lambda item: item[1], reverse=True
                        )
                    ],
                }
            )
            sections.append(
                {
                    "title": "Prescription Volume",
                    "headers": ["Metric", "Value"],
                    "rows": [
                        ["Total Prescriptions", str(len(prescriptions))],
                        ["Active Prescriptions", str(active_prescriptions)],
                        ["Unique Drugs", str(len(prescription_counts))],
                    ],
                }
            )
        if pending_surgeries:
            sections.append(
                {
                    "title": "Pending Surgery Backlog (surgery-type treatments without post-op notes)",
                    "headers": ["Treatment ID", "Dog ID", "Vet ID", "Date"],
                    "rows": [
                        [
                            str(t.id),
                            str(t.dog_id),
                            str(t.vet_id),
                            t.treatment_date.date()
                            if hasattr(t.treatment_date, "date")
                            else t.treatment_date,
                        ]
                        for t in pending_surgeries
                    ],
                }
            )

        return {
            "title": "Medical Treatment Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": ["ID", "Dog ID", "Vet ID", "Treatment Type", "Date"],
            "rows": [
                [
                    str(m.id),
                    str(m.dog_id),
                    str(m.vet_id),
                    m.treatment_type,
                    m.treatment_date.date()
                    if hasattr(m.treatment_date, "date")
                    else m.treatment_date,
                ]
                for m in treatments
            ],
            "sections": sections,
        }

    async def _fetch_medical_treatments(self, start: date | None, end: date | None):
        stmt = select(MedicalTreatment)
        if start:
            stmt = stmt.where(MedicalTreatment.treatment_date >= start)
        if end:
            stmt = stmt.where(MedicalTreatment.treatment_date <= end)
        return (await self._session.execute(stmt)).scalars().all()

    async def _fetch_vaccinations(self, start: date | None, end: date | None):
        stmt = select(VaccinationRecord)
        if start:
            stmt = stmt.where(VaccinationRecord.administered_at >= start)
        if end:
            stmt = stmt.where(VaccinationRecord.administered_at <= end)
        return (await self._session.execute(stmt)).scalars().all()

    async def _fetch_prescriptions(self, start: date | None, end: date | None):
        stmt = select(Prescription)
        if start:
            stmt = stmt.where(Prescription.start_at >= start)
        if end:
            stmt = stmt.where(Prescription.start_at <= end)
        return (await self._session.execute(stmt)).scalars().all()

    async def _fetch_total_dogs(self):
        return (
            await self._session.execute(
                select(func.count(DogProfile.id)).where(DogProfile.deleted_at.is_(None))
            )
        ).scalar() or 0

    async def _inventory_report(self, filters: dict[str, Any] | None) -> dict[str, Any]:
        stmt = select(InventoryItem)
        if filters and "category" in filters:
            stmt = stmt.where(InventoryItem.category == filters["category"])
        results = (await self._session.execute(stmt)).scalars().all()
        movements = (await self._session.execute(select(InventoryMovement))).scalars().all()
        requisitions = (await self._session.execute(select(RequisitionOrder))).scalars().all()

        total_value = sum(float(i.quantity * i.unit_cost) for i in results)
        item_costs = {str(i.id): float(i.unit_cost) for i in results}

        # Movement / usage analytics (PRR 4.1 Inventory Consumption & Expiry
        # Audit): volume by reference type and movement direction, movement
        # speed (avg interval), and loss / write-off value (negative
        # adjustments valued at the item's unit cost).
        movement_by_ref: dict[str, dict[str, dict]] = {}
        write_off_value = 0.0
        check_in_total = check_out_total = adjustment_total = 0.0
        timestamps: list[datetime] = []
        for m in movements:
            reference = m.reference_type or "unspecified"
            mtype = m.movement_type
            bucket = movement_by_ref.setdefault(reference, {}).setdefault(
                mtype, {"quantity": 0.0, "count": 0}
            )
            qty = float(m.quantity)
            bucket["quantity"] += qty
            bucket["count"] += 1
            if mtype == MovementType.CHECK_IN:
                check_in_total += qty
            elif mtype == MovementType.CHECK_OUT:
                check_out_total += qty
            elif mtype == MovementType.ADJUSTMENT:
                adjustment_total += qty
                if qty < 0:
                    write_off_value += abs(qty) * item_costs.get(str(m.item_id), 0.0)
            timestamp = _coerce_utc(m.created_at)
            if timestamp is not None:
                timestamps.append(timestamp)
        timestamps.sort()
        gaps = [
            (later - earlier).total_seconds() / 86400.0
            for earlier, later in zip(timestamps, timestamps[1:], strict=True)
        ]
        avg_movement_interval = sum(gaps) / len(gaps) if gaps else None

        today = date.today()
        expired_items = [i for i in results if i.expiry_date is not None and i.expiry_date < today]
        expired_value = sum(float(i.quantity * i.unit_cost) for i in expired_items)

        reorder_items = [i for i in results if float(i.quantity) <= float(i.reorder_threshold)]
        pending_requisitions = [r for r in requisitions if r.status == RequisitionStatus.PENDING]
        requisition_status_counts: dict[str, int] = {}
        for r in requisitions:
            requisition_status_counts[r.status] = requisition_status_counts.get(r.status, 0) + 1

        headers = [
            "ID",
            "Name",
            "Category",
            "Quantity",
            "Unit",
            "Reorder Threshold",
            "Unit Cost",
            "Total Value",
        ]
        rows = [
            [
                str(i.id),
                i.name,
                i.category,
                float(i.quantity),
                i.unit,
                float(i.reorder_threshold),
                float(i.unit_cost),
                float(i.quantity * i.unit_cost),
            ]
            for i in results
        ] + ([["", "", "", "", "", "", "TOTAL", f"{total_value:.2f}"]] if results else [])

        sections = []
        if movements:
            movement_rows = []
            for reference, type_buckets in sorted(movement_by_ref.items()):
                in_qty = type_buckets.get(MovementType.CHECK_IN, {"quantity": 0.0})["quantity"]
                out_qty = type_buckets.get(MovementType.CHECK_OUT, {"quantity": 0.0})["quantity"]
                adj_qty = type_buckets.get(MovementType.ADJUSTMENT, {"quantity": 0.0})["quantity"]
                movement_rows.append(
                    [
                        reference,
                        f"{in_qty:.1f}",
                        f"{out_qty:.1f}",
                        f"{adj_qty:.1f}",
                        str(sum(bucket["count"] for bucket in type_buckets.values())),
                    ]
                )
            movement_rows.append(
                [
                    "TOTAL",
                    f"{check_in_total:.1f}",
                    f"{check_out_total:.1f}",
                    f"{adjustment_total:.1f}",
                    str(len(movements)),
                ]
            )
            sections.append(
                {
                    "title": "Movement & Usage Summary",
                    "headers": [
                        "Reference Type",
                        "Check-In Qty",
                        "Check-Out Qty",
                        "Adjustment Qty",
                        "Movement Count",
                    ],
                    "rows": movement_rows,
                }
            )
        sections.append(
            {
                "title": "Inventory Health Metrics",
                "headers": ["Metric", "Value"],
                "rows": [
                    ["Total Items", str(len(results))],
                    ["Total Inventory Value", f"{total_value:.2f}"],
                    ["Expired Value", f"{expired_value:.2f}"],
                    ["Write-off / Loss Value", f"{write_off_value:.2f}"],
                    [
                        "Avg Movement Interval (days)",
                        f"{avg_movement_interval:.1f}"
                        if avg_movement_interval is not None
                        else "N/A",
                    ],
                ],
            }
        )
        if expired_items:
            sections.append(
                {
                    "title": "Expired Items",
                    "headers": [
                        "Name",
                        "Category",
                        "Quantity",
                        "Expiry Date",
                        "Unit Cost",
                        "Value",
                    ],
                    "rows": [
                        [
                            i.name,
                            i.category,
                            float(i.quantity),
                            i.expiry_date,
                            float(i.unit_cost),
                            float(i.quantity * i.unit_cost),
                        ]
                        for i in expired_items
                    ],
                }
            )
        if reorder_items:
            sections.append(
                {
                    "title": "Reorder in Progress (Below Threshold)",
                    "headers": ["Name", "Quantity", "Reorder Threshold", "Unit"],
                    "rows": [
                        [i.name, float(i.quantity), float(i.reorder_threshold), i.unit]
                        for i in reorder_items
                    ],
                }
            )
        if pending_requisitions:
            sections.append(
                {
                    "title": "Pending Requisition Orders",
                    "headers": ["Requisition ID", "Item ID", "Quantity", "Status"],
                    "rows": [
                        [str(r.id), str(r.item_id), float(r.quantity), r.status]
                        for r in pending_requisitions
                    ],
                }
            )
        if requisitions:
            sections.append(
                {
                    "title": "Requisition Volume",
                    "headers": ["Status", "Count"],
                    "rows": [
                        [status, str(count)]
                        for status, count in sorted(requisition_status_counts.items())
                    ],
                }
            )

        return {
            "title": "Inventory Report",
            "headers": headers,
            "rows": rows,
            "sections": sections,
        }

    async def _rescue_report(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        stmt = select(RescueRequest, RescueDispatch).outerjoin(
            RescueDispatch, RescueDispatch.rescue_request_id == RescueRequest.id
        )
        if start:
            stmt = stmt.where(RescueRequest.created_at >= start)
        if end:
            stmt = stmt.where(RescueRequest.created_at <= end)
        if filters and "status" in filters:
            stmt = stmt.where(RescueRequest.status == filters["status"])
        joined = (await self._session.execute(stmt)).all()

        req_map: dict[uuid.UUID, RescueRequest] = {}
        pairs: list[tuple[RescueRequest, RescueDispatch]] = []
        for row in joined:
            req, disp = row[0], row[1]
            if req.id not in req_map:
                req_map[req.id] = req
            if disp is not None:
                pairs.append((req, disp))

        results = list(req_map.values())
        dispatches = [dispatch for _, dispatch in pairs]

        headers = [
            "ID",
            "Ticket",
            "Status",
            "Reporter",
            "Location",
            "Animal Count",
            "Created",
        ]
        rows = [
            [
                str(r.id),
                r.ticket_number,
                r.status,
                r.reporter_name,
                r.location_address,
                r.animal_count,
                r.created_at.date() if r.created_at else "",
            ]
            for r in results
        ]
        rows = mask_report_data(rows, headers, {"Reporter"})

        # Geo heatmap (PRR 3.2): aggregate rescue cases by ~1km grid cell so
        # staff can spot incident hotspots. Cells without coordinates are
        # excluded from the map but reported as a count.
        geo_counts: dict[tuple[float, float], int] = {}
        cases_without_coords = 0
        for r in results:
            if r.latitude is None or r.longitude is None:
                cases_without_coords += 1
                continue
            lat = round(float(r.latitude), 2)
            lng = round(float(r.longitude), 2)
            geo_counts[(lat, lng)] = geo_counts.get((lat, lng), 0) + 1
        geo_rows = [
            [f"{lat:.2f}", f"{lng:.2f}", count]
            for (lat, lng), count in sorted(
                geo_counts.items(), key=lambda item: item[1], reverse=True
            )
        ]
        geo_title = "Geo Heatmap (Rescue Locations)"
        if cases_without_coords:
            geo_title += f" — {cases_without_coords} case(s) without coordinates"

        sections = []
        if geo_rows:
            sections.append(
                {
                    "title": geo_title,
                    "headers": ["Latitude", "Longitude", "Cases"],
                    "rows": geo_rows,
                }
            )

        # Dispatch & response analytics (PRR 4.1 Rescue Case Efficiency):
        # average response time, success ratio, failure-reason breakdown and
        # per-status distribution.
        if results:
            total = len(results)
            successful = sum(
                1 for r in results if r.status in (RescueStatus.RESCUED, RescueStatus.ADMITTED)
            )
            response_times: list[float] = []
            for request, dispatch in pairs:
                disp_time = dispatch.dispatched_at or dispatch.created_at
                req_time = request.created_at
                if disp_time and req_time:
                    if disp_time.tzinfo is not None and req_time.tzinfo is None:
                        req_time = req_time.replace(tzinfo=UTC)
                    elif disp_time.tzinfo is None and req_time.tzinfo is not None:
                        disp_time = disp_time.replace(tzinfo=UTC)
                    diff_hours = (disp_time - req_time).total_seconds() / 3600.0
                    if diff_hours >= 0:
                        response_times.append(diff_hours)

            avg_response_time = (
                sum(response_times) / len(response_times) if response_times else None
            )

            status_counts: dict[str, int] = {}
            for r in results:
                status_counts[r.status] = status_counts.get(r.status, 0) + 1
            sections.append(
                {
                    "title": "Rescue Outcomes by Status",
                    "headers": ["Status", "Count"],
                    "rows": [
                        [status, str(count)] for status, count in sorted(status_counts.items())
                    ],
                }
            )
            sections.append(
                {
                    "title": "Dispatch & Response Analytics",
                    "headers": ["Metric", "Value"],
                    "rows": [
                        ["Total Rescue Requests", str(total)],
                        ["Dispatched", str(len(pairs))],
                        ["Successful (Rescued/Admitted)", str(successful)],
                        ["Success Ratio", f"{successful / total * 100.0:.1f}%"],
                        [
                            "Avg Response Time",
                            f"{avg_response_time:.1f}h" if avg_response_time is not None else "N/A",
                        ],
                    ],
                }
            )

            failure_counts: dict[str, int] = {}
            for dispatch in dispatches:
                if dispatch.failure_reason:
                    failure_counts[dispatch.failure_reason] = (
                        failure_counts.get(dispatch.failure_reason, 0) + 1
                    )
            if failure_counts:
                sections.append(
                    {
                        "title": "Failure Reason Breakdown",
                        "headers": ["Failure Reason", "Count"],
                        "rows": [
                            [reason, str(count)]
                            for reason, count in sorted(
                                failure_counts.items(), key=lambda item: item[1], reverse=True
                            )
                        ],
                    }
                )

            if dispatches:
                dispatch_rows = [
                    [
                        str(d.id),
                        str(d.rescue_request_id),
                        str(d.assigned_driver_id) if d.assigned_driver_id else "",
                        str(d.vehicle_id or ""),
                        d.dispatched_at.strftime("%Y-%m-%d %H:%M:%S") if d.dispatched_at else "",
                        str(d.failure_reason or ""),
                    ]
                    for d in dispatches
                ]
                sections.append(
                    {
                        "title": "Dispatch Log",
                        "headers": [
                            "Dispatch ID",
                            "Request ID",
                            "Assigned Driver",
                            "Vehicle",
                            "Dispatched At",
                            "Failure Reason",
                        ],
                        "rows": dispatch_rows,
                    }
                )

        return {
            "title": "Rescue Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": headers,
            "rows": rows,
            "sections": sections,
        }

    async def _finance_report(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        # Parallelise independent DB reads.
        transactions_task = asyncio.ensure_future(
            self._fetch_financial_transactions(start, end, filters)
        )
        donations_task = asyncio.ensure_future(self._fetch_donations_for_finance(start, end))
        gl_task = asyncio.ensure_future(self._fetch_gl_summary())
        inventory_value_task = asyncio.ensure_future(self._fetch_inventory_value())
        rescued_dogs_task = asyncio.ensure_future(self._fetch_rescued_dogs_count())
        transactions, donations, gl_rows_raw, inventory_value, rescued_dogs = await asyncio.gather(
            transactions_task,
            donations_task,
            gl_task,
            inventory_value_task,
            rescued_dogs_task,
        )
        inventory_value = float(inventory_value)
        rescued_dogs = int(rescued_dogs)

        # GL / summary analytics (PRR 4.1 Financial Transparency).
        total_expenses = sum(
            float(t.amount)
            for t in transactions
            if t.transaction_type == TransactionType.EXPENSE
            and t.status not in (TransactionStatus.VOIDED,)
        )
        cost_per_dog = (total_expenses / rescued_dogs) if rescued_dogs else 0.0

        donation_group: dict[tuple[str, str], dict] = {}
        successful_donations_by_donor: dict[str, int] = {}
        for d in donations:
            key = (d.donation_type, d.status)
            entry = donation_group.setdefault(key, {"count": 0, "total": 0.0})
            entry["count"] += 1
            entry["total"] += float(d.amount)
            if d.status == DonationStatus.SUCCESS:
                donor_key = str(d.donor_id)
                successful_donations_by_donor[donor_key] = (
                    successful_donations_by_donor.get(donor_key, 0) + 1
                )
        total_donors = len(successful_donations_by_donor)
        repeat_donors = sum(1 for count in successful_donations_by_donor.values() if count > 1)
        retention_rate = (repeat_donors / total_donors * 100.0) if total_donors else 0.0

        sections = []
        if donation_group:
            sections.append(
                {
                    "title": "Donation Totals",
                    "headers": ["Donation Type", "Status", "Count", "Total Amount"],
                    "rows": [
                        [donation_type, status, str(info["count"]), f"{info['total']:.2f}"]
                        for (donation_type, status), info in sorted(donation_group.items())
                    ],
                }
            )
            sections.append(
                {
                    "title": "Donor Retention",
                    "headers": ["Metric", "Value"],
                    "rows": [
                        ["Successful Donors", str(total_donors)],
                        ["Repeat Donors (>1 donation)", str(repeat_donors)],
                        ["Donor Retention Rate", f"{retention_rate:.1f}%"],
                    ],
                }
            )
        if gl_rows_raw:
            sections.append(
                {
                    "title": "GL Summary by Category",
                    "headers": ["Category", "Income (Credits)", "Expense (Debits)", "Net"],
                    "rows": [
                        [
                            str(row[0]),
                            f"{float(row[1]):.2f}",
                            f"{float(row[2]):.2f}",
                            f"{float(row[1]) - float(row[2]):.2f}",
                        ]
                        for row in gl_rows_raw
                    ],
                }
            )
        sections.append(
            {
                "title": "Cost Analysis",
                "headers": ["Metric", "Value"],
                "rows": [
                    ["Total Inventory Cost Exposure", f"{inventory_value:.2f}"],
                    ["Total Expenses", f"{total_expenses:.2f}"],
                    ["Dogs Rescued (Admitted via Rescue)", str(rescued_dogs)],
                    ["Cost per Rescued Dog", f"{cost_per_dog:.2f}"],
                ],
            }
        )

        return {
            "title": "Finance Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": [
                "ID",
                "Number",
                "Type",
                "Amount",
                "Currency",
                "Status",
                "Date",
            ],
            "rows": [
                [
                    str(t.id),
                    t.transaction_number,
                    t.transaction_type,
                    float(t.amount),
                    t.currency,
                    t.status,
                    t.transaction_date,
                ]
                for t in transactions
            ],
            "sections": sections,
        }

    async def _fetch_financial_transactions(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ):
        stmt = select(FinancialTransaction).where(FinancialTransaction.deleted_at.is_(None))
        if start:
            stmt = stmt.where(FinancialTransaction.transaction_date >= start)
        if end:
            stmt = stmt.where(FinancialTransaction.transaction_date <= end)
        if filters and "type" in filters:
            stmt = stmt.where(FinancialTransaction.transaction_type == filters["type"])
        if filters and "status" in filters:
            stmt = stmt.where(FinancialTransaction.status == filters["status"])
        return (await self._session.execute(stmt)).scalars().all()

    async def _fetch_donations_for_finance(self, start: date | None, end: date | None):
        stmt = select(Donation)
        if start:
            stmt = stmt.where(Donation.created_at >= start)
        if end:
            stmt = stmt.where(Donation.created_at <= end)
        return (await self._session.execute(stmt)).scalars().all()

    async def _fetch_gl_summary(self):
        stmt = (
            select(
                ChartOfAccounts.category,
                func.coalesce(func.sum(GeneralLedgerEntry.credit_amount), 0),
                func.coalesce(func.sum(GeneralLedgerEntry.debit_amount), 0),
            )
            .join(GeneralLedgerEntry, GeneralLedgerEntry.account_id == ChartOfAccounts.id)
            .group_by(ChartOfAccounts.category)
            .order_by(ChartOfAccounts.category)
        )
        return (await self._session.execute(stmt)).all()

    async def _fetch_inventory_value(self):
        return (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(InventoryItem.quantity * InventoryItem.unit_cost), 0)
                ).where(InventoryItem.deleted_at.is_(None))
            )
        ).scalar() or 0.0

    async def _fetch_rescued_dogs_count(self):
        return (
            await self._session.execute(
                select(func.count(DogProfile.id)).where(
                    DogProfile.deleted_at.is_(None),
                    DogProfile.rescue_case_id.isnot(None),
                )
            )
        ).scalar() or 0

    @staticmethod
    def _months_in_range(start: date | None, end: date | None) -> int:
        if not start or not end:
            return 1
        return max(1, (end.year - start.year) * 12 + end.month - start.month + 1)

    async def _shelter_report(
        self, start: date | None, end: date | None, filters: dict | None
    ) -> dict:
        facilities = (
            (
                await self._session.execute(
                    select(ShelterFacility).where(ShelterFacility.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        facility_names = {str(f.id): f.name for f in facilities}

        # Kennel counts / capacity per facility (kennels belong to sections,
        # sections belong to facilities).
        kennel_stmt = (
            select(
                ShelterFacility.id,
                func.count(Kennel.id),
                func.coalesce(func.sum(Kennel.capacity), 0),
            )
            .select_from(ShelterFacility)
            .join(ShelterSection, ShelterSection.facility_id == ShelterFacility.id)
            .join(Kennel, Kennel.section_id == ShelterSection.id)
            .group_by(ShelterFacility.id)
        )
        kennel_rows = (await self._session.execute(kennel_stmt)).all()
        kennel_stats = {
            str(row[0]): {"count": int(row[1]), "capacity": float(row[2])} for row in kennel_rows
        }

        # Dogs housed, occupied kennels and average length of stay (non-adopted
        # dogs only: now() - created_at).
        dog_stmt = (
            select(
                DogProfile.shelter_facility_id,
                func.count(DogProfile.id),
                func.count(DogProfile.kennel_id),
                func.avg(func.extract("epoch", func.now() - DogProfile.created_at) / 86400.0),
            )
            .where(
                DogProfile.deleted_at.is_(None),
                DogProfile.shelter_facility_id.isnot(None),
                DogProfile.status != DogStatus.ADOPTED,
            )
            .group_by(DogProfile.shelter_facility_id)
        )
        dog_rows = (await self._session.execute(dog_stmt)).all()
        dog_stats = {
            str(row[0]): {
                "dogs": int(row[1]),
                "occupied": int(row[2]),
                "avg_los": float(row[3]) if row[3] is not None else None,
            }
            for row in dog_rows
        }

        # Intake / admission log: DogProfile rows created per facility.
        intake_stmt = (
            select(DogProfile, ShelterFacility.name)
            .join(ShelterFacility, ShelterFacility.id == DogProfile.shelter_facility_id)
            .where(
                DogProfile.deleted_at.is_(None),
                DogProfile.shelter_facility_id.isnot(None),
            )
            .order_by(ShelterFacility.name, DogProfile.created_at)
        )
        intake_rows = (await self._session.execute(intake_stmt)).all()

        # Quarantine-to-clear speed: no explicit quarantine timestamps exist, so
        # the proxy is intake (DogProfile.created_at) -> first vaccination
        # record for dogs that have passed quarantine.
        quarantine_stmt = (
            select(
                DogProfile.shelter_facility_id,
                DogProfile.created_at,
                func.min(VaccinationRecord.administered_at),
            )
            .join(VaccinationRecord, VaccinationRecord.dog_id == DogProfile.id)
            .where(
                DogProfile.deleted_at.is_(None),
                DogProfile.is_quarantine_passed.is_(True),
                DogProfile.shelter_facility_id.isnot(None),
            )
            .group_by(DogProfile.id, DogProfile.shelter_facility_id, DogProfile.created_at)
        )
        quarantine_rows = (await self._session.execute(quarantine_stmt)).all()
        quarantine_days: dict[str, list[float]] = {}
        for row in quarantine_rows:
            created = _coerce_utc(row[1])
            cleared = _coerce_utc(row[2])
            if created is None or cleared is None:
                continue
            days = max(0.0, (cleared - created).total_seconds() / 86400.0)
            quarantine_days.setdefault(str(row[0]), []).append(days)
        quarantine_avg = {key: sum(values) / len(values) for key, values in quarantine_days.items()}

        # Facility transfer volumes (in / out per facility).
        transfers = (await self._session.execute(select(FacilityTransfer))).scalars().all()
        transfers_in: dict[str, int] = {}
        transfers_out: dict[str, int] = {}
        transfers_in_completed: dict[str, int] = {}
        transfers_out_completed: dict[str, int] = {}
        for t in transfers:
            to_key = str(t.to_facility_id)
            from_key = str(t.from_facility_id)
            transfers_in[to_key] = transfers_in.get(to_key, 0) + 1
            transfers_out[from_key] = transfers_out.get(from_key, 0) + 1
            if t.status == TransferStatus.COMPLETED:
                transfers_in_completed[to_key] = transfers_in_completed.get(to_key, 0) + 1
                transfers_out_completed[from_key] = transfers_out_completed.get(from_key, 0) + 1

        headers = [
            "ID",
            "Name",
            "Status",
            "Type",
            "Total Capacity",
            "Kennels",
            "Kennel Capacity",
            "Dogs Housed",
            "Avg LOS (days)",
            "Facility Utilization %",
        ]
        main_rows = []
        kennel_util_rows = []
        for f in facilities:
            key = str(f.id)
            ks = kennel_stats.get(key, {"count": 0, "capacity": 0.0})
            ds = dog_stats.get(key, {"dogs": 0, "occupied": 0, "avg_los": None})
            facility_util = (
                round(ds["dogs"] / float(f.total_capacity) * 100, 1) if f.total_capacity else 0.0
            )
            kennel_util = round(ds["occupied"] / ks["count"] * 100, 1) if ks["count"] else 0.0
            main_rows.append(
                [
                    key,
                    f.name,
                    f.status,
                    f.facility_type,
                    f.total_capacity,
                    ks["count"],
                    f"{ks['capacity']:.1f}",
                    ds["dogs"],
                    f"{ds['avg_los']:.1f}" if ds["avg_los"] is not None else "",
                    f"{facility_util:.1f}",
                ]
            )
            kennel_util_rows.append(
                [
                    f.name,
                    ks["count"],
                    f"{ks['capacity']:.1f}",
                    ds["occupied"],
                    f"{kennel_util:.1f}",
                ]
            )

        intake_log_rows = [
            [
                facility_name,
                str(dog.id),
                dog.registration_number,
                dog.name,
                dog.status,
                dog.created_at.date() if hasattr(dog.created_at, "date") else dog.created_at,
            ]
            for dog, facility_name in intake_rows
        ]

        quarantine_rows_out = [
            [facility_names.get(key, key), f"{days:.1f}"]
            for key, days in sorted(quarantine_avg.items())
        ]

        transfer_rows = [
            [
                f.name,
                transfers_in.get(str(f.id), 0),
                transfers_out.get(str(f.id), 0),
                transfers_in_completed.get(str(f.id), 0),
                transfers_out_completed.get(str(f.id), 0),
            ]
            for f in facilities
        ]

        sections = []
        if kennel_util_rows:
            sections.append(
                {
                    "title": "Kennel Capacity & Utilization",
                    "headers": [
                        "Facility",
                        "Kennel Count",
                        "Kennel Capacity",
                        "Occupied Kennels",
                        "Kennel Utilization %",
                    ],
                    "rows": kennel_util_rows,
                }
            )
        if intake_log_rows:
            sections.append(
                {
                    "title": "Intake & Admission Log",
                    "headers": [
                        "Facility",
                        "Dog ID",
                        "Registration #",
                        "Name",
                        "Status",
                        "Admitted At",
                    ],
                    "rows": intake_log_rows,
                }
            )
        if quarantine_rows_out:
            sections.append(
                {
                    "title": "Quarantine-to-Clear Speed (proxy: intake to first vaccination)",
                    "headers": ["Facility", "Avg Days to Clear"],
                    "rows": quarantine_rows_out,
                }
            )
        if transfer_rows:
            sections.append(
                {
                    "title": "Facility Transfer Volumes",
                    "headers": [
                        "Facility",
                        "Transfers In",
                        "Transfers Out",
                        "Completed In",
                        "Completed Out",
                    ],
                    "rows": transfer_rows,
                }
            )

        return {
            "title": "Shelter Report",
            "subtitle": f"{start or 'N/A'} to {end or 'N/A'}",
            "headers": headers,
            "rows": main_rows,
            "sections": sections,
        }

    async def _staff_performance_report(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        months = self._months_in_range(start, end)

        # Parallelise all independent DB reads (8 sequential queries → 1 gather).
        total_adoptions_task = asyncio.ensure_future(self._count_adoptions_completed(start, end))
        active_foster_task = asyncio.ensure_future(self._count_active_fosters())
        total_placements_task = asyncio.ensure_future(self._count_foster_placements())
        returned_placements_task = asyncio.ensure_future(self._count_returned_placements())
        rescue_count_task = asyncio.ensure_future(self._count_rescue_requests(start, end))
        avg_response_task = asyncio.ensure_future(self._avg_rescue_response(start, end))
        medical_count_task = asyncio.ensure_future(self._count_medical_treatments(start, end))
        dogs_in_care_task = asyncio.ensure_future(self._count_dogs_in_care())
        avg_los_task = asyncio.ensure_future(self._avg_los())
        volunteer_count_task = asyncio.ensure_future(self._count_active_volunteers())

        (
            total_adoptions,
            active_foster,
            total_placements,
            returned_placements,
            rescue_count,
            avg_response_time,
            medical_count,
            dogs_in_care,
            avg_los,
            volunteer_count,
        ) = await asyncio.gather(
            total_adoptions_task,
            active_foster_task,
            total_placements_task,
            returned_placements_task,
            rescue_count_task,
            avg_response_task,
            medical_count_task,
            dogs_in_care_task,
            avg_los_task,
            volunteer_count_task,
        )

        adoption_velocity = total_adoptions / months
        foster_efficiency = (
            (returned_placements / total_placements * 100) if total_placements else 0.0
        )
        avg_response_time = round(avg_response_time, 1) if avg_response_time is not None else None
        avg_los = round(avg_los, 1) if avg_los is not None else None

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

    async def _count_adoptions_completed(self, start: date | None, end: date | None):
        stmt = select(func.count(AdoptionApplication.id)).where(
            AdoptionApplication.status == AdoptionStatus.COMPLETED
        )
        if start:
            stmt = stmt.where(AdoptionApplication.created_at >= start)
        if end:
            stmt = stmt.where(AdoptionApplication.created_at <= end)
        return (await self._session.execute(stmt)).scalar() or 0

    async def _count_active_fosters(self):
        return (
            await self._session.execute(
                select(func.count(FosterPlacement.id)).where(FosterPlacement.is_active.is_(True))
            )
        ).scalar() or 0

    async def _count_foster_placements(self):
        return (await self._session.execute(select(func.count(FosterPlacement.id)))).scalar() or 0

    async def _count_returned_placements(self):
        return (
            await self._session.execute(
                select(func.count(FosterPlacement.id)).where(
                    FosterPlacement.returned_at.isnot(None)
                )
            )
        ).scalar() or 0

    async def _count_rescue_requests(self, start: date | None, end: date | None):
        stmt = select(func.count(RescueRequest.id))
        if start:
            stmt = stmt.where(RescueRequest.created_at >= start)
        if end:
            stmt = stmt.where(RescueRequest.created_at <= end)
        return (await self._session.execute(stmt)).scalar() or 0

    async def _avg_rescue_response(self, start: date | None, end: date | None):
        response_time_expr = (
            func.extract("epoch", RescueDispatch.dispatched_at - RescueRequest.created_at) / 3600.0
        )
        stmt = (
            select(func.avg(response_time_expr))
            .select_from(RescueDispatch)
            .join(RescueRequest, RescueDispatch.rescue_request_id == RescueRequest.id)
        )
        if start:
            stmt = stmt.where(RescueRequest.created_at >= start)
        if end:
            stmt = stmt.where(RescueRequest.created_at <= end)
        return (await self._session.execute(stmt)).scalar()

    async def _count_medical_treatments(self, start: date | None, end: date | None):
        stmt = select(func.count(MedicalTreatment.id))
        if start:
            stmt = stmt.where(MedicalTreatment.treatment_date >= start)
        if end:
            stmt = stmt.where(MedicalTreatment.treatment_date <= end)
        return (await self._session.execute(stmt)).scalar() or 0

    async def _count_dogs_in_care(self):
        return (
            await self._session.execute(
                select(func.count(DogProfile.id)).where(DogProfile.status != DogStatus.ADOPTED)
            )
        ).scalar() or 0

    async def _avg_los(self):
        return (
            await self._session.execute(
                select(
                    func.avg(func.extract("epoch", func.now() - DogProfile.created_at) / 86400.0)
                ).where(DogProfile.status != DogStatus.ADOPTED)
            )
        ).scalar()

    async def _count_active_volunteers(self):
        return (
            await self._session.execute(
                select(func.count(VolunteerProfile.id)).where(VolunteerProfile.status == "active")
            )
        ).scalar() or 0

    async def _animal_population_report(self, filters: dict[str, Any] | None) -> dict[str, Any]:
        stmt = select(DogProfile)
        if filters and "status" in filters:
            stmt = stmt.where(DogProfile.status == filters["status"])
        if filters and "breed" in filters:
            stmt = stmt.where(DogProfile.breed == filters["breed"])
        results = (await self._session.execute(stmt)).scalars().all()
        return {
            "title": "Animal Population Report",
            "headers": [
                "ID",
                "Name",
                "Breed",
                "Gender",
                "Status",
                "Age",
                "Weight",
            ],
            "rows": [
                [
                    str(d.id),
                    d.name,
                    d.breed,
                    d.gender,
                    d.status,
                    d.estimated_age or "",
                    float(d.weight) if d.weight else "",
                ]
                for d in results
            ],
        }

    async def _foster_report(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
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
                "ID",
                "Foster ID",
                "Dog ID",
                "Placed At",
                "Returned At",
                "Active",
            ],
            "rows": [
                [
                    str(f.id),
                    str(f.foster_id),
                    str(f.dog_id),
                    f.placed_at.date() if hasattr(f.placed_at, "date") else f.placed_at,
                    f.returned_at.date() if f.returned_at else "",
                    "Yes" if f.is_active else "No",
                ]
                for f in results
            ],
        }

    async def _volunteer_report(
        self, start: date | None, end: date | None, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        stmt = select(VolunteerProfile)
        if filters and "status" in filters:
            stmt = stmt.where(VolunteerProfile.status == filters["status"])
        results = (await self._session.execute(stmt)).scalars().all()
        return {
            "title": "Volunteer Report",
            "headers": ["ID", "User ID", "Status", "Skills", "Available"],
            "rows": [
                [
                    str(v.id),
                    str(v.user_id),
                    v.status,
                    v.skills or "",
                    "Yes" if v.status == VolunteerStatus.ACTIVE else "No",
                ]
                for v in results
            ],
        }
