from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.donation.models import Donation, DonationStatus
from pawguard.modules.finance.models import (
    FinancialTransaction,
    TransactionStatus,
    TransactionType,
)
from pawguard.modules.foster.models import FosterPlacement
from pawguard.modules.grievance.models import GrievanceStatus, GrievanceTicket
from pawguard.modules.inventory.models import InventoryItem
from pawguard.modules.medical.models import ClinicalExam, MedicalTreatment
from pawguard.modules.rescue.models import RescueRequest, RescueStatus
from pawguard.modules.shelter.models import Kennel, ShelterFacility
from pawguard.modules.volunteer.models import VolunteerProfile, VolunteerStatus


def _ts_range(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def rescue_dashboard(session: AsyncSession) -> dict[str, Any]:
    total = await session.execute(select(func.count(RescueRequest.id)))
    pending = await session.execute(
        select(func.count(RescueRequest.id)).where(
            RescueRequest.status == RescueStatus.REPORTED
        )
    )
    dispatched = await session.execute(
        select(func.count(RescueRequest.id)).where(
            RescueRequest.status == RescueStatus.DISPATCHED
        )
    )
    rescued = await session.execute(
        select(func.count(RescueRequest.id)).where(
            RescueRequest.status == RescueStatus.RESCUED
        )
    )
    recent = await session.execute(
        select(RescueRequest).order_by(RescueRequest.created_at.desc()).limit(10)
    )
    recent_list = [
        {
            "id": str(r.id),
            "ticket": r.ticket_number,
            "status": r.status,
            "reporter": r.reporter_name,
            "animal_count": r.animal_count,
            "created_at": r.created_at.isoformat(),
        }
        for r in recent.scalars().all()
    ]
    return {
        "total_calls": total.scalar_one(),
        "pending": pending.scalar_one(),
        "dispatched": dispatched.scalar_one(),
        "rescued": rescued.scalar_one(),
        "recent_calls": recent_list,
    }


async def shelter_dashboard(session: AsyncSession) -> dict[str, Any]:
    facilities = await session.execute(select(func.count(ShelterFacility.id)))
    dogs = await session.execute(select(func.count(DogProfile.id)))
    adoptable = await session.execute(
        select(func.count(DogProfile.id)).where(
            DogProfile.status == DogStatus.SHELTER
        )
    )
    kennels = await session.execute(select(func.count(Kennel.id)))
    total_dogs = dogs.scalar_one()
    total_kennels = kennels.scalar_one()
    return {
        "total_facilities": facilities.scalar_one(),
        "total_dogs": total_dogs,
        "adoptable_dogs": adoptable.scalar_one(),
        "total_kennels": total_kennels,
        "occupancy_rate": (
            round(total_dogs / total_kennels * 100, 1) if total_kennels > 0 else 0
        ),
    }


async def medical_dashboard(session: AsyncSession) -> dict[str, Any]:
    recent = _ts_range(30)
    exams = await session.execute(
        select(func.count(ClinicalExam.id)).where(
            ClinicalExam.exam_date >= recent
        )
    )
    treatments = await session.execute(
        select(func.count(MedicalTreatment.id)).where(
            MedicalTreatment.treatment_date >= recent
        )
    )
    return {
        "exams_last_30d": exams.scalar_one(),
        "treatments_last_30d": treatments.scalar_one(),
    }


async def adoption_dashboard(session: AsyncSession) -> dict[str, Any]:
    total = await session.execute(select(func.count(AdoptionApplication.id)))
    pending = await session.execute(
        select(func.count(AdoptionApplication.id)).where(
            AdoptionApplication.status == AdoptionStatus.SUBMITTED
        )
    )
    approved = await session.execute(
        select(func.count(AdoptionApplication.id)).where(
            AdoptionApplication.status == AdoptionStatus.APPROVED
        )
    )
    completed = await session.execute(
        select(func.count(AdoptionApplication.id)).where(
            AdoptionApplication.status == AdoptionStatus.COMPLETED
        )
    )
    return {
        "total_applications": total.scalar_one(),
        "pending": pending.scalar_one(),
        "approved": approved.scalar_one(),
        "completed": completed.scalar_one(),
    }


async def foster_dashboard(session: AsyncSession) -> dict[str, Any]:
    total = await session.execute(select(func.count(FosterPlacement.id)))
    active = await session.execute(
        select(func.count(FosterPlacement.id)).where(
            FosterPlacement.is_active.is_(True)
        )
    )
    return {
        "total_placements": total.scalar_one(),
        "active_placements": active.scalar_one(),
    }


async def volunteer_dashboard(session: AsyncSession) -> dict[str, Any]:
    total = await session.execute(select(func.count(VolunteerProfile.id)))
    available = await session.execute(
        select(func.count(VolunteerProfile.id)).where(
            VolunteerProfile.status == VolunteerStatus.ACTIVE.value
        )
    )
    return {
        "total_volunteers": total.scalar_one(),
        "available": available.scalar_one(),
    }


async def inventory_dashboard(session: AsyncSession) -> dict[str, Any]:
    items = await session.execute(
        select(
            InventoryItem.category,
            func.count(InventoryItem.id),
            func.sum(InventoryItem.quantity),
        ).group_by(InventoryItem.category)
    )
    low_stock = await session.execute(
        select(InventoryItem).where(
            InventoryItem.quantity <= InventoryItem.reorder_threshold
        )
    )
    categories = [
        {
            "category": row[0],
            "count": row[1],
            "total_quantity": float(row[2]) if row[2] else 0,
        }
        for row in items.all()
    ]
    low_items = [
        {
            "id": str(i.id),
            "name": i.name,
            "quantity": float(i.quantity),
            "threshold": float(i.reorder_threshold),
        }
        for i in low_stock.scalars().all()
    ]
    return {
        "categories": categories,
        "low_stock_alerts": low_items,
        "total_low_stock": len(low_items),
    }


async def finance_dashboard(session: AsyncSession) -> dict[str, Any]:
    posted = [TransactionStatus.POSTED, TransactionStatus.RECONCILED]
    income = await session.execute(
        select(func.coalesce(func.sum(FinancialTransaction.amount), 0)).where(
            FinancialTransaction.transaction_type == TransactionType.INCOME,
            FinancialTransaction.status.in_(posted),
            FinancialTransaction.deleted_at.is_(None),
        )
    )
    expense = await session.execute(
        select(func.coalesce(func.sum(FinancialTransaction.amount), 0)).where(
            FinancialTransaction.transaction_type == TransactionType.EXPENSE,
            FinancialTransaction.status.in_(posted),
            FinancialTransaction.deleted_at.is_(None),
        )
    )
    pending_tx = await session.execute(
        select(func.count(FinancialTransaction.id)).where(
            FinancialTransaction.status == TransactionStatus.PENDING,
            FinancialTransaction.deleted_at.is_(None),
        )
    )
    total_income = float(income.scalar_one())
    total_expenses = float(expense.scalar_one())
    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_balance": total_income - total_expenses,
        "pending_transactions": pending_tx.scalar_one(),
    }


async def donor_dashboard(session: AsyncSession) -> dict[str, Any]:
    total = await session.execute(
        select(
            func.count(Donation.id),
            func.coalesce(func.sum(Donation.amount), 0),
        ).where(Donation.status == DonationStatus.SUCCESS)
    )
    total_count, total_amount = total.one()
    recent = _ts_range(30)
    recent_donations = await session.execute(
        select(Donation).where(
            Donation.created_at >= recent,
            Donation.status == DonationStatus.SUCCESS,
        ).order_by(Donation.created_at.desc()).limit(10)
    )
    return {
        "total_donations": total_count,
        "total_amount": float(total_amount),
        "recent_donations": [
            {
                "id": str(d.id),
                "amount": float(d.amount),
                "currency": d.currency,
                "type": d.donation_type,
                "date": d.created_at.date().isoformat(),
            }
            for d in recent_donations.scalars().all()
        ],
    }


async def staff_dashboard(session: AsyncSession) -> dict[str, Any]:
    users = await session.execute(select(func.count(User.id)))
    grievances = await session.execute(
        select(func.count(GrievanceTicket.id)).where(
            GrievanceTicket.status == GrievanceStatus.OPEN.value
        )
    )
    return {
        "total_staff": users.scalar_one(),
        "open_grievances": grievances.scalar_one(),
    }


async def executive_dashboard(session: AsyncSession) -> dict[str, Any]:
    rescue = await rescue_dashboard(session)
    finance = await finance_dashboard(session)
    adoption = await adoption_dashboard(session)
    return {
        "rescue_overview": {
            "total_calls": rescue["total_calls"],
            "rescued": rescue["rescued"],
        },
        "finance_overview": {
            "total_income": finance["total_income"],
            "total_expenses": finance["total_expenses"],
            "net_balance": finance["net_balance"],
        },
        "adoption_overview": {
            "total": adoption["total_applications"],
            "completed": adoption["completed"],
        },
    }


async def public_dashboard(session: AsyncSession) -> dict[str, Any]:
    adoptable = await session.execute(
        select(func.count(DogProfile.id)).where(
            DogProfile.status == DogStatus.SHELTER
        )
    )
    rescued = await session.execute(
        select(func.count(RescueRequest.id)).where(
            RescueRequest.status == RescueStatus.RESCUED
        )
    )
    return {
        "adoptable_dogs": adoptable.scalar_one(),
        "dogs_rescued": rescued.scalar_one(),
    }


async def operations_dashboard(session: AsyncSession) -> dict[str, Any]:
    rescue = await rescue_dashboard(session)
    shelter = await shelter_dashboard(session)
    inventory = await inventory_dashboard(session)
    return {
        "rescue": {
            "pending": rescue["pending"],
            "dispatched": rescue["dispatched"],
        },
        "shelter": {
            "occupancy_rate": shelter["occupancy_rate"],
            "total_dogs": shelter["total_dogs"],
        },
        "inventory": {
            "low_stock_count": inventory["total_low_stock"],
        },
    }
