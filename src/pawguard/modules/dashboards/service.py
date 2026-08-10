import json
from contextlib import suppress
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

DASHBOARD_CACHE_TTL = 30  # seconds


async def _get_cached(redis: Any | None, key: str) -> dict[str, Any] | None:
    if redis is None:
        return None
    with suppress(Exception):
        data = await redis.get(key)
        if data:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data)  # type: ignore[no-any-return]
    return None


async def _set_cache(
    redis: Any | None, key: str, data: dict[str, Any], ttl: int = DASHBOARD_CACHE_TTL
) -> None:
    if redis is None:
        return
    with suppress(Exception):
        await redis.set(key, json.dumps(data), ex=ttl)



def _ts_range(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def rescue_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:rescue"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

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
    result = {
        "total_calls": total.scalar_one(),
        "pending": pending.scalar_one(),
        "dispatched": dispatched.scalar_one(),
        "rescued": rescued.scalar_one(),
        "recent_calls": recent_list,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def shelter_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:shelter"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

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
    result = {
        "total_facilities": facilities.scalar_one(),
        "total_dogs": total_dogs,
        "adoptable_dogs": adoptable.scalar_one(),
        "total_kennels": total_kennels,
        "occupancy_rate": (
            round(total_dogs / total_kennels * 100, 1) if total_kennels > 0 else 0
        ),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def medical_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:medical"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

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
    result = {
        "exams_last_30d": exams.scalar_one(),
        "treatments_last_30d": treatments.scalar_one(),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def adoption_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:adoption"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

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
    result = {
        "total_applications": total.scalar_one(),
        "pending": pending.scalar_one(),
        "approved": approved.scalar_one(),
        "completed": completed.scalar_one(),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def foster_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:foster"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    total = await session.execute(select(func.count(FosterPlacement.id)))
    active = await session.execute(
        select(func.count(FosterPlacement.id)).where(
            FosterPlacement.is_active.is_(True)
        )
    )
    result = {
        "total_placements": total.scalar_one(),
        "active_placements": active.scalar_one(),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def volunteer_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:volunteer"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    total = await session.execute(select(func.count(VolunteerProfile.id)))
    available = await session.execute(
        select(func.count(VolunteerProfile.id)).where(
            VolunteerProfile.status == VolunteerStatus.ACTIVE.value
        )
    )
    result = {
        "total_volunteers": total.scalar_one(),
        "available": available.scalar_one(),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def inventory_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:inventory"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

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
    result = {
        "categories": categories,
        "low_stock_alerts": low_items,
        "total_low_stock": len(low_items),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def finance_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:finance"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    posted = [TransactionStatus.POSTED, TransactionStatus.RECONCILED]
    income = await session.execute(
        select(func.coalesce(func.sum(FinancialTransaction.amount), 0)).where(
            FinancialTransaction.transaction_type == TransactionType.INCOME,
            FinancialTransaction.status.in_(posted),
            FinancialTransaction.deleted_at.is_(None),
        )
    )
    donation_income = await session.execute(
        select(func.coalesce(func.sum(FinancialTransaction.amount), 0)).where(
            FinancialTransaction.transaction_type == TransactionType.RECONCILIATION,
            FinancialTransaction.status.in_(posted),
            FinancialTransaction.deleted_at.is_(None),
        )
    )
    unreconciled_donations = await session.execute(
        select(func.coalesce(func.sum(Donation.amount), 0)).where(
            Donation.status == DonationStatus.SUCCESS,
            Donation.id.notin_(
                select(FinancialTransaction.donation_id).where(
                    FinancialTransaction.donation_id.isnot(None),
                    FinancialTransaction.status == TransactionStatus.RECONCILED,
                )
            ),
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
    total_income = (
        float(income.scalar_one())
        + float(donation_income.scalar_one())
        + float(unreconciled_donations.scalar_one())
    )
    total_expenses = float(expense.scalar_one())
    result = {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_balance": total_income - total_expenses,
        "pending_transactions": pending_tx.scalar_one(),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def donor_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:donor"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

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
    result = {
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
    await _set_cache(redis, cache_key, result)
    return result


async def staff_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:staff"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    users = await session.execute(select(func.count(User.id)))
    grievances = await session.execute(
        select(func.count(GrievanceTicket.id)).where(
            GrievanceTicket.status == GrievanceStatus.OPEN.value
        )
    )
    result = {
        "total_staff": users.scalar_one(),
        "open_grievances": grievances.scalar_one(),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def executive_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:executive"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    rescue = await rescue_dashboard(session, redis=redis)
    finance = await finance_dashboard(session, redis=redis)
    adoption = await adoption_dashboard(session, redis=redis)
    result = {
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
    await _set_cache(redis, cache_key, result)
    return result


async def public_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:public"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

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
    result = {
        "adoptable_dogs": adoptable.scalar_one(),
        "dogs_rescued": rescued.scalar_one(),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def operations_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    cache_key = "cache:dashboard:operations"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    rescue = await rescue_dashboard(session, redis=redis)
    shelter = await shelter_dashboard(session, redis=redis)
    inventory = await inventory_dashboard(session, redis=redis)
    result = {
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
    await _set_cache(redis, cache_key, result)
    return result

