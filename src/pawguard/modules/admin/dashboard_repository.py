"""DashboardRepository: data access for admin dashboard metrics (RULE-002)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth.models import AuthAuditLog, Role, User, UserSession
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.donation.models import Donation, DonationStatus
from pawguard.modules.foster.models import FosterPlacement, FosterProfile
from pawguard.modules.grievance.models import GrievanceStatus, GrievanceTicket, ServiceFeedback
from pawguard.modules.inventory.models import InventoryItem
from pawguard.modules.lost_found.models import FoundReport, LostReport
from pawguard.modules.medical.models import ClinicalExam, MedicalTreatment, VaccinationRecord
from pawguard.modules.notifications.models import Notification
from pawguard.modules.rescue.models import RescueRequest, RescueStatus
from pawguard.modules.shelter.models import ShelterFacility
from pawguard.modules.volunteer.models import ShiftAttendance, VolunteerProfile


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_total_users_count(self) -> int:
        result = await self._session.execute(select(func.count(User.id)))
        return result.scalar_one()

    async def get_active_users_count(self) -> int:
        stmt = select(func.count()).select_from(User).where(User.is_active.is_(True))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_verified_users_count(self) -> int:
        stmt = select(func.count()).select_from(User).where(User.is_verified.is_(True))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_total_roles_count(self) -> int:
        result = await self._session.execute(select(func.count(Role.id)))
        return result.scalar_one()

    async def get_active_sessions_count(self) -> int:
        stmt = select(func.count(UserSession.id)).where(UserSession.is_active.is_(True))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_rescues_by_status(self) -> dict[str, int]:
        stmt = select(RescueRequest.status, func.count(RescueRequest.id))
        stmt = stmt.where(RescueRequest.deleted_at.is_(None)).group_by(RescueRequest.status)
        rows = (await self._session.execute(stmt)).all()
        return {str(r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in rows}

    async def count_dogs_by_status(self) -> dict[str, int]:
        stmt = select(DogProfile.status, func.count(DogProfile.id))
        stmt = stmt.where(DogProfile.deleted_at.is_(None)).group_by(DogProfile.status)
        rows = (await self._session.execute(stmt)).all()
        return {str(r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in rows}

    async def count_adoptions_by_status(self) -> dict[str, int]:
        stmt = select(AdoptionApplication.status, func.count(AdoptionApplication.id))
        stmt = stmt.where(AdoptionApplication.deleted_at.is_(None))
        stmt = stmt.group_by(AdoptionApplication.status)
        rows = (await self._session.execute(stmt)).all()
        return {str(r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in rows}

    async def count_volunteers_by_status(self) -> dict[str, int]:
        stmt = select(VolunteerProfile.status, func.count(VolunteerProfile.id))
        stmt = stmt.where(VolunteerProfile.deleted_at.is_(None)).group_by(VolunteerProfile.status)
        rows = (await self._session.execute(stmt)).all()
        return {str(r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in rows}

    async def count_grievances_by_status(self) -> dict[str, int]:
        stmt = select(GrievanceTicket.status, func.count(GrievanceTicket.id))
        stmt = stmt.where(GrievanceTicket.deleted_at.is_(None)).group_by(GrievanceTicket.status)
        rows = (await self._session.execute(stmt)).all()
        return {str(r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in rows}

    async def get_donation_totals(self) -> dict[str, Any]:
        stmt = select(
            func.count(Donation.id),
            func.coalesce(
                func.sum(Donation.amount).filter(Donation.status == DonationStatus.SUCCESS), 0
            ),
        )
        total_count, total_amount = (await self._session.execute(stmt)).one()
        return {"total_donations": total_count, "total_raised": float(total_amount)}

    async def get_recent_donations(self, days: int = 30) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = select(
            func.count(Donation.id),
            func.coalesce(
                func.sum(Donation.amount).filter(Donation.status == DonationStatus.SUCCESS), 0
            ),
        ).where(Donation.created_at >= since)
        count, amount = (await self._session.execute(stmt)).one()
        return {"donation_count": count, "amount_raised": float(amount)}

    async def get_adoption_rate(self) -> float:
        total_stmt = select(func.count(DogProfile.id)).where(DogProfile.deleted_at.is_(None))
        total = (await self._session.execute(total_stmt)).scalar_one()
        if total == 0:
            return 0.0
        adopted = (
            await self._session.execute(
                select(func.count(DogProfile.id)).where(
                    DogProfile.deleted_at.is_(None), DogProfile.status == DogStatus.ADOPTED
                )
            )
        ).scalar_one()
        return round(adopted / total * 100, 1)

    async def get_shelter_occupancy(self) -> dict[str, Any]:
        total_capacity = (
            await self._session.execute(
                select(func.coalesce(func.sum(ShelterFacility.total_capacity), 0))
            )
        ).scalar_one()
        dogs_in_shelter = (
            await self._session.execute(
                select(func.count(DogProfile.id)).where(
                    DogProfile.deleted_at.is_(None),
                    DogProfile.status.in_([DogStatus.SHELTER, DogStatus.CLINIC]),
                )
            )
        ).scalar_one()
        occupancy_pct = round(dogs_in_shelter / total_capacity * 100, 1) if total_capacity else 0.0
        return {
            "capacity": total_capacity,
            "occupied": dogs_in_shelter,
            "occupancy_pct": occupancy_pct,
        }

    async def get_inventory_alerts(self) -> list[dict[str, Any]]:
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.quantity <= InventoryItem.reorder_threshold)
            .order_by(InventoryItem.quantity.asc())
        )
        items = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "id": str(i.id),
                "name": i.name,
                "category": i.category,
                "quantity": i.quantity,
                "reorder_threshold": i.reorder_threshold,
            }
            for i in items
        ]

    async def count_expiring_inventory(self, days: int = 30) -> int:
        from datetime import date, timedelta

        threshold = date.today() + timedelta(days=days)
        stmt = select(func.count(InventoryItem.id)).where(
            InventoryItem.expiry_date.isnot(None),
            InventoryItem.expiry_date <= threshold,
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def get_recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        stmt = select(AuthAuditLog).order_by(AuthAuditLog.created_at.desc()).limit(limit)
        entries = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "id": str(e.id),
                "user_id": str(e.user_id) if e.user_id else None,
                "event_type": e.event_type,
                "ip_address": e.ip_address,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]

    async def get_rescue_kpis(self) -> dict[str, Any]:
        total = (
            await self._session.execute(
                select(func.count(RescueRequest.id)).where(RescueRequest.deleted_at.is_(None))
            )
        ).scalar_one()
        resolved = (
            await self._session.execute(
                select(func.count(RescueRequest.id)).where(
                    RescueRequest.deleted_at.is_(None),
                    RescueRequest.status == RescueStatus.ADMITTED,
                )
            )
        ).scalar_one()
        rejection_rate = 0.0
        if total > 0:
            rejected = (
                await self._session.execute(
                    select(func.count(RescueRequest.id)).where(
                        RescueRequest.deleted_at.is_(None),
                        RescueRequest.status == RescueStatus.REJECTED,
                    )
                )
            ).scalar_one()
            rejection_rate = round(rejected / total * 100, 1)
        avg_response = await self._get_avg_rescue_response_time()
        return {
            "total_rescues": total,
            "admitted": resolved,
            "rejection_rate_pct": rejection_rate,
            "avg_response_time_minutes": round(avg_response, 1) if avg_response else None,
        }

    async def _get_avg_rescue_response_time(self) -> float | None:
        from pawguard.modules.rescue.models import RescueDispatch

        stmt = select(
            func.avg(
                func.extract("epoch", RescueDispatch.located_at - RescueDispatch.dispatched_at) / 60
            )
        ).where(
            RescueDispatch.located_at.isnot(None),
            RescueDispatch.dispatched_at.isnot(None),
        )
        result = (await self._session.execute(stmt)).scalar()
        return float(result) if result is not None else None

    async def get_medical_stats(self) -> dict[str, Any]:
        exams = (await self._session.execute(select(func.count(ClinicalExam.id)))).scalar_one()
        treatments = (
            await self._session.execute(select(func.count(MedicalTreatment.id)))
        ).scalar_one()
        vaccinations = (
            await self._session.execute(select(func.count(VaccinationRecord.id)))
        ).scalar_one()
        return {
            "total_exams": exams,
            "total_treatments": treatments,
            "total_vaccinations": vaccinations,
        }

    async def get_volunteer_hours(self) -> float:
        result = await self._session.execute(
            select(func.coalesce(func.sum(ShiftAttendance.hours_logged), 0))
        )
        return float(result.scalar_one() or 0.0)

    async def get_active_fosters(self) -> int:
        stmt = select(func.count(FosterPlacement.id)).where(FosterPlacement.is_active.is_(True))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_open_grievances(self) -> int:
        stmt = select(func.count(GrievanceTicket.id)).where(
            GrievanceTicket.deleted_at.is_(None),
            GrievanceTicket.status.in_(
                [
                    GrievanceStatus.OPEN,
                    GrievanceStatus.INVESTIGATING,
                    GrievanceStatus.AWAITING_RESPONSE,
                ]
            ),
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def get_unread_notifications_count(self) -> int:
        stmt = select(func.count(Notification.id)).where(Notification.is_read.is_(False))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_active_lost_found(self) -> dict[str, Any]:
        lost_stmt = select(func.count(LostReport.id)).where(
            LostReport.deleted_at.is_(None), LostReport.status == "active"
        )
        found_stmt = select(func.count(FoundReport.id)).where(
            FoundReport.deleted_at.is_(None), FoundReport.status == "active"
        )
        lost = (await self._session.execute(lost_stmt)).scalar_one()
        found = (await self._session.execute(found_stmt)).scalar_one()
        return {"active_lost": lost, "active_found": found}

    async def get_foster_stats(self) -> dict[str, Any]:
        total_profiles = (
            await self._session.execute(
                select(func.count(FosterProfile.id)).where(FosterProfile.deleted_at.is_(None))
            )
        ).scalar_one()
        available = (
            await self._session.execute(
                select(func.count(FosterProfile.id)).where(
                    FosterProfile.deleted_at.is_(None), FosterProfile.is_available.is_(True)
                )
            )
        ).scalar_one()
        active = await self.get_active_fosters()
        return {
            "total_fosters": total_profiles,
            "available": available,
            "active_placements": active,
        }

    async def get_monthly_adoption_trend(self, months: int = 6) -> list[dict[str, Any]]:
        from sqlalchemy import extract

        since = datetime.now(UTC) - timedelta(days=months * 30)
        stmt = (
            select(
                extract("year", AdoptionApplication.created_at).label("year"),
                extract("month", AdoptionApplication.created_at).label("month"),
                func.count(AdoptionApplication.id),
            )
            .where(
                AdoptionApplication.deleted_at.is_(None),
                AdoptionApplication.created_at >= since,
            )
            .group_by("year", "month")
            .order_by("year", "month")
        )
        rows = (await self._session.execute(stmt)).all()
        return [{"year": int(r.year), "month": int(r.month), "count": r.count} for r in rows]

    async def get_monthly_rescue_trend(self, months: int = 6) -> list[dict[str, Any]]:
        from sqlalchemy import extract

        since = datetime.now(UTC) - timedelta(days=months * 30)
        stmt = (
            select(
                extract("year", RescueRequest.created_at).label("year"),
                extract("month", RescueRequest.created_at).label("month"),
                func.count(RescueRequest.id),
            )
            .where(
                RescueRequest.deleted_at.is_(None),
                RescueRequest.created_at >= since,
            )
            .group_by("year", "month")
            .order_by("year", "month")
        )
        rows = (await self._session.execute(stmt)).all()
        return [{"year": int(r.year), "month": int(r.month), "count": r.count} for r in rows]

    async def get_monthly_donation_trend(self, months: int = 6) -> list[dict[str, Any]]:
        from sqlalchemy import extract

        since = datetime.now(UTC) - timedelta(days=months * 30)
        stmt = (
            select(
                extract("year", Donation.created_at).label("year"),
                extract("month", Donation.created_at).label("month"),
                func.count(Donation.id),
                func.coalesce(
                    func.sum(Donation.amount).filter(Donation.status == DonationStatus.SUCCESS), 0
                ),
            )
            .where(
                Donation.created_at >= since,
            )
            .group_by("year", "month")
            .order_by("year", "month")
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {"year": int(r.year), "month": int(r.month), "count": r.count, "amount": float(r[3])}
            for r in rows
        ]

    async def get_dog_breed_distribution(self) -> list[dict[str, Any]]:
        stmt = (
            select(DogProfile.breed, func.count(DogProfile.id))
            .where(DogProfile.deleted_at.is_(None))
            .group_by(DogProfile.breed)
            .order_by(func.count(DogProfile.id).desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [{"breed": r.breed, "count": r.count} for r in rows]

    async def get_feedback_summary(self) -> dict[str, Any]:
        total = (
            await self._session.execute(
                select(func.count(ServiceFeedback.id)).where(ServiceFeedback.deleted_at.is_(None))
            )
        ).scalar_one()
        avg_rating = (
            await self._session.execute(select(func.coalesce(func.avg(ServiceFeedback.rating), 0)))
        ).scalar_one()
        return {"total_feedback": total, "average_rating": round(float(avg_rating), 1)}

    async def get_total_dogs_count(self) -> int:
        stmt = select(func.count(DogProfile.id)).where(DogProfile.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_adoptable_dogs_count(self) -> int:
        stmt = select(func.count(DogProfile.id)).where(
            DogProfile.deleted_at.is_(None), DogProfile.is_adoptable.is_(True)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def get_pending_adoptions_count(self) -> int:
        stmt = select(func.count(AdoptionApplication.id)).where(
            AdoptionApplication.deleted_at.is_(None),
            AdoptionApplication.status == AdoptionStatus.SUBMITTED,
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def get_total_rescues_count(self) -> int:
        stmt = select(func.count(RescueRequest.id)).where(RescueRequest.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_total_notifications_count(self) -> int:
        stmt = select(func.count(Notification.id))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_total_volunteers_count(self) -> int:
        stmt = select(func.count(VolunteerProfile.id)).where(VolunteerProfile.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_total_facilities_count(self) -> int:
        stmt = select(func.count(ShelterFacility.id))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_total_lost_count(self) -> int:
        stmt = select(func.count(LostReport.id)).where(LostReport.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_total_found_count(self) -> int:
        stmt = select(func.count(FoundReport.id)).where(FoundReport.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one()

    async def get_system_metrics(self) -> dict[str, int]:
        """Single-query replacement for the old asyncio.gather multi-query approach."""
        stmt = text("""
            SELECT
                (SELECT COUNT(*) FROM users WHERE deleted_at IS NULL) AS total_users,
                (SELECT COUNT(*) FROM users WHERE is_active = true AND deleted_at IS NULL) AS active_users,
                (SELECT COUNT(*) FROM users WHERE is_verified = true AND deleted_at IS NULL) AS verified_users,
                (SELECT COUNT(*) FROM roles) AS total_roles,
                (SELECT COUNT(*) FROM user_sessions WHERE is_active = true) AS active_sessions,
                (SELECT COUNT(*) FROM dog_profiles WHERE deleted_at IS NULL) AS total_dogs,
                (SELECT COUNT(*) FROM dog_profiles WHERE is_adoptable = true AND deleted_at IS NULL) AS adoptable_dogs,
                (SELECT COUNT(*) FROM adoption_applications WHERE status = 'submitted' AND deleted_at IS NULL) AS pending_adoptions,
                (SELECT COUNT(*) FROM rescue_requests WHERE deleted_at IS NULL) AS total_rescues
        """)
        row = (await self._session.execute(stmt)).one()
        return {
            "total_users": row.total_users,
            "active_users": row.active_users,
            "verified_users": row.verified_users,
            "total_roles": row.total_roles,
            "active_sessions": row.active_sessions,
            "total_dogs": row.total_dogs,
            "adoptable_dogs": row.adoptable_dogs,
            "pending_adoptions": row.pending_adoptions,
            "total_rescues": row.total_rescues,
        }

    async def get_summary(self) -> dict[str, Any]:
        stmt = text("""
            SELECT
                (SELECT COUNT(*) FROM users WHERE deleted_at IS NULL) AS total_users,
                (SELECT COUNT(*) FROM users WHERE is_active = true AND deleted_at IS NULL) AS active_users,
                (SELECT COUNT(*) FROM users WHERE is_verified = true AND deleted_at IS NULL) AS verified_users,
                (SELECT COUNT(*) FROM dog_profiles WHERE deleted_at IS NULL) AS total_dogs,
                (SELECT COUNT(*) FROM dog_profiles WHERE is_adoptable = true AND deleted_at IS NULL) AS adoptable_dogs,
                (SELECT COUNT(*) FROM rescue_requests WHERE deleted_at IS NULL) AS total_rescues,
                (SELECT COUNT(*) FROM adoption_applications WHERE status = 'submitted') AS pending_adoptions,
                (SELECT COUNT(*) FROM volunteer_profiles) AS total_volunteers,
                (SELECT COUNT(*) FROM grievance_tickets WHERE status != 'resolved' AND deleted_at IS NULL) AS open_grievances,
                (SELECT COUNT(*) FROM notifications WHERE is_read = false) AS unread_notifications,
                (SELECT COUNT(*) FROM notifications) AS total_notifications
        """)
        row = (await self._session.execute(stmt)).one()
        (
            total_users,
            active_users,
            verified_users,
            total_dogs,
            adoptable_dogs,
            total_rescues,
            pending_adoptions,
            total_volunteers,
            open_grievances,
            unread_notifications,
            total_notifications,
        ) = row

        dogs_by_status = await self.count_dogs_by_status()
        rescues_by_status = await self.count_rescues_by_status()
        adoptions_by_status = await self.count_adoptions_by_status()
        adoption_rate = await self.get_adoption_rate()
        donations = await self.get_donation_totals()
        shelters = await self.get_shelter_occupancy()
        volunteers_by_status = await self.count_volunteers_by_status()
        volunteer_hours = await self.get_volunteer_hours()
        grievances_by_status = await self.count_grievances_by_status()
        lost_found = await self.get_active_lost_found()
        fosters = await self.get_foster_stats()
        return {
            "users": {
                "total_users": total_users,
                "active_users": active_users,
                "verified_users": verified_users,
            },
            "dogs": {
                "total_dogs": total_dogs,
                "adoptable_dogs": adoptable_dogs,
                "by_status": dogs_by_status,
            },
            "rescues": {
                "total": total_rescues,
                "by_status": rescues_by_status,
            },
            "adoptions": {
                "by_status": adoptions_by_status,
                "adoption_rate_pct": adoption_rate,
                "pending": pending_adoptions,
            },
            "donations": donations,
            "shelters": shelters,
            "volunteers": {
                "total": total_volunteers,
                "by_status": volunteers_by_status,
                "hours_logged": volunteer_hours,
            },
            "grievances": {
                "open": open_grievances,
                "by_status": grievances_by_status,
            },
            "lost_found": lost_found,
            "notifications": {
                "unread": unread_notifications,
                "total": total_notifications,
            },
            "fosters": fosters,
        }

    async def get_kpis(self) -> dict[str, Any]:
        """Single combined SQL query for all KPI metrics — 1 DB round-trip instead of 16+."""
        stmt = text("""
            SELECT
                -- Adoption rate: adopted / total dogs
                COALESCE(
                    ROUND(
                        100.0 * COUNT(DISTINCT CASE WHEN dp.status = 'adopted' AND dp.deleted_at IS NULL THEN dp.id END)
                        / NULLIF(COUNT(DISTINCT CASE WHEN dp.deleted_at IS NULL THEN dp.id END), 0),
                        1
                    ), 0
                ) AS adoption_rate_pct,
                -- Shelter occupancy
                COALESCE(SUM(DISTINCT sf.total_capacity), 0) AS shelter_capacity,
                (SELECT COUNT(*) FROM dog_profiles WHERE status IN ('shelter','clinic') AND deleted_at IS NULL) AS dogs_in_shelter,
                -- Rescue KPIs
                (SELECT COUNT(*) FROM rescue_requests WHERE deleted_at IS NULL) AS total_rescues,
                (SELECT COUNT(*) FROM rescue_requests WHERE status = 'rejected' AND deleted_at IS NULL) AS rejected_rescues,
                (SELECT AVG(EXTRACT(EPOCH FROM (rd.located_at - rd.dispatched_at)) / 60)
                 FROM rescue_dispatches rd WHERE rd.located_at IS NOT NULL AND rd.dispatched_at IS NOT NULL
                ) AS avg_response_minutes,
                -- Donations
                COALESCE((SELECT SUM(amount) FROM donations WHERE status = 'success'), 0) AS total_raised,
                -- Grievances
                (SELECT COUNT(*) FROM grievance_tickets
                 WHERE status IN ('open','investigating','awaiting_response') AND deleted_at IS NULL
                ) AS open_grievances,
                -- Notifications
                (SELECT COUNT(*) FROM notifications WHERE is_read = false) AS unread_notifications,
                -- Fosters
                (SELECT COUNT(*) FROM foster_placements WHERE is_active = true) AS active_fosters,
                -- Volunteer hours
                COALESCE((SELECT SUM(hours_logged) FROM shift_attendances), 0) AS volunteer_hours
            FROM dog_profiles dp
            CROSS JOIN shelter_facilities sf
        """)
        row = (await self._session.execute(stmt)).one()
        total_rescues = row.total_rescues or 0
        rejected_rescues = row.rejected_rescues or 0
        rejection_rate = (
            round(rejected_rescues / total_rescues * 100, 1) if total_rescues > 0 else 0.0
        )
        shelter_capacity = row.shelter_capacity or 0
        dogs_in_shelter = row.dogs_in_shelter or 0
        occupancy_pct = (
            round(dogs_in_shelter / shelter_capacity * 100, 1) if shelter_capacity > 0 else 0.0
        )
        return {
            "adoption_rate_pct": float(row.adoption_rate_pct or 0),
            "shelter_occupancy_pct": occupancy_pct,
            "rescue_rejection_rate_pct": rejection_rate,
            "avg_rescue_response_minutes": round(float(row.avg_response_minutes), 1)
            if row.avg_response_minutes
            else None,
            "total_raised": float(row.total_raised or 0),
            "open_grievances": row.open_grievances or 0,
            "unread_notifications": row.unread_notifications or 0,
            "active_fosters": row.active_fosters or 0,
            "volunteer_hours": float(row.volunteer_hours or 0),
        }

    async def get_charts(self) -> dict[str, Any]:
        adoption_trend = await self.get_monthly_adoption_trend()
        rescue_trend = await self.get_monthly_rescue_trend()
        donation_trend = await self.get_monthly_donation_trend()
        breed_distribution = await self.get_dog_breed_distribution()
        return {
            "adoption_trend": adoption_trend,
            "rescue_trend": rescue_trend,
            "donation_trend": donation_trend,
            "breed_distribution": breed_distribution,
        }

    async def get_donation_summary(self) -> dict[str, Any]:
        totals = await self.get_donation_totals()
        recent = await self.get_recent_donations(days=30)
        trend = await self.get_monthly_donation_trend(months=6)
        return {
            "total_donations": totals["total_donations"],
            "total_raised": totals["total_raised"],
            "recent_30d": recent,
            "monthly_trend": trend,
        }

    async def get_rescue_stats(self) -> dict[str, Any]:
        """Single query: rescue KPIs + status breakdown in one round-trip."""
        stmt = text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'admitted') AS admitted,
                COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
                COUNT(*) FILTER (WHERE status = 'reported') AS reported,
                COUNT(*) FILTER (WHERE status = 'verified') AS verified,
                COUNT(*) FILTER (WHERE status = 'dispatched') AS dispatched,
                COUNT(*) FILTER (WHERE status = 'located') AS located,
                COUNT(*) FILTER (WHERE status = 'rescued') AS rescued,
                (SELECT AVG(EXTRACT(EPOCH FROM (located_at - dispatched_at)) / 60)
                 FROM rescue_dispatches WHERE located_at IS NOT NULL AND dispatched_at IS NOT NULL
                ) AS avg_response_minutes
            FROM rescue_requests
            WHERE deleted_at IS NULL
        """)
        row = (await self._session.execute(stmt)).one()
        total = row.total or 0
        rejected = row.rejected or 0
        rejection_rate = round(rejected / total * 100, 1) if total > 0 else 0.0
        return {
            "total_rescues": total,
            "admitted": row.admitted or 0,
            "rejection_rate_pct": rejection_rate,
            "avg_response_time_minutes": round(float(row.avg_response_minutes), 1)
            if row.avg_response_minutes
            else None,
            "by_status": {
                "reported": row.reported or 0,
                "verified": row.verified or 0,
                "dispatched": row.dispatched or 0,
                "located": row.located or 0,
                "rescued": row.rescued or 0,
                "admitted": row.admitted or 0,
                "rejected": row.rejected or 0,
            },
        }

    async def get_adoption_stats(self) -> dict[str, Any]:
        """Single query: adoption status counts + rate in one round-trip."""
        stmt = text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'submitted') AS submitted,
                COUNT(*) FILTER (WHERE status = 'screening') AS screening,
                COUNT(*) FILTER (WHERE status = 'interview') AS interview,
                COUNT(*) FILTER (WHERE status = 'home_check') AS home_check,
                COUNT(*) FILTER (WHERE status = 'approved') AS approved,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
                COUNT(*) FILTER (WHERE status = 'withdrawn') AS withdrawn
            FROM adoption_applications
            WHERE deleted_at IS NULL
        """)
        row = (await self._session.execute(stmt)).one()
        by_status = {
            "submitted": row.submitted or 0,
            "screening": row.screening or 0,
            "interview": row.interview or 0,
            "home_check": row.home_check or 0,
            "approved": row.approved or 0,
            "completed": row.completed or 0,
            "rejected": row.rejected or 0,
            "withdrawn": row.withdrawn or 0,
        }
        total = row.total or 0
        completed = row.completed or 0
        # Fetch trend separately (needs GROUP BY month, can't combine with above)
        trend = await self.get_monthly_adoption_trend()
        adoption_rate_pct = round(completed / total * 100, 1) if total > 0 else 0.0
        return {
            "by_status": by_status,
            "adoption_rate_pct": adoption_rate_pct,
            "pending": row.submitted or 0,
            "monthly_trend": trend,
        }

    async def get_volunteer_stats(self) -> dict[str, Any]:
        total = await self.get_total_volunteers_count()
        by_status = await self.count_volunteers_by_status()
        hours = await self.get_volunteer_hours()
        return {
            "total_volunteers": total,
            "by_status": by_status,
            "hours_logged": hours,
        }

    async def get_notification_summary(self) -> dict[str, Any]:
        """Single query for notification counts — 1 round-trip instead of 2."""
        stmt = text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE is_read = false) AS unread
            FROM notifications
        """)
        row = (await self._session.execute(stmt)).one()
        total = row.total or 0
        unread = row.unread or 0
        return {
            "total": total,
            "unread": unread,
            "read": total - unread,
        }

    async def get_shelter_stats(self) -> dict[str, Any]:
        """Single query for shelter stats — 1 round-trip instead of 3."""
        stmt = text("""
            SELECT
                (SELECT COUNT(*) FROM shelter_facilities) AS total_facilities,
                COALESCE((SELECT SUM(total_capacity) FROM shelter_facilities), 0) AS capacity,
                (SELECT COUNT(*) FROM dog_profiles WHERE status IN ('shelter','clinic') AND deleted_at IS NULL) AS occupied
        """)
        row = (await self._session.execute(stmt)).one()
        capacity = row.capacity or 0
        occupied = row.occupied or 0
        occupancy_pct = round(occupied / capacity * 100, 1) if capacity > 0 else 0.0
        return {
            "total_facilities": row.total_facilities or 0,
            "capacity": capacity,
            "occupied": occupied,
            "occupancy_pct": occupancy_pct,
        }

    async def get_lost_found_stats(self) -> dict[str, Any]:
        active = await self.get_active_lost_found()
        total_lost = await self.get_total_lost_count()
        total_found = await self.get_total_found_count()
        return {
            "active_lost": active["active_lost"],
            "active_found": active["active_found"],
            "total_lost": total_lost,
            "total_found": total_found,
        }

    async def get_grievance_stats(self) -> dict[str, Any]:
        open_g = await self.get_open_grievances()
        by_status = await self.count_grievances_by_status()
        feedback = await self.get_feedback_summary()
        return {
            "open": open_g,
            "by_status": by_status,
            "feedback": feedback,
        }
