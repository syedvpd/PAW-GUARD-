import json
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.auth.models import Role, User, UserRole
from pawguard.modules.donation.models import Donation, DonationStatus
from pawguard.modules.fleet.models import Vehicle
from pawguard.modules.inventory.models import InventoryItem
from pawguard.modules.medical.models import ClinicalExam, MedicalTreatment
from pawguard.modules.rescue.models import (
    RescueDispatch,
    RescueDispatchAgent,
    RescueRequest,
    RescueStatus,
)

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


async def rescue_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:rescue"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    counts_stmt = select(
        func.count(RescueRequest.id).label("total"),
        func.count(RescueRequest.id)
        .filter(RescueRequest.status == RescueStatus.REPORTED)
        .label("pending"),
        func.count(RescueRequest.id)
        .filter(RescueRequest.status == RescueStatus.DISPATCHED)
        .label("dispatched"),
        func.count(RescueRequest.id)
        .filter(RescueRequest.status == RescueStatus.RESCUED)
        .label("rescued"),
    )
    counts_row = (await session.execute(counts_stmt)).one()

    recent_res = await session.execute(
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
        for r in recent_res.scalars().all()
    ]
    result = {
        "total_calls": counts_row.total,
        "pending": counts_row.pending,
        "dispatched": counts_row.dispatched,
        "rescued": counts_row.rescued,
        "recent_calls": recent_list,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def rescue_operations_dashboard(
    session: AsyncSession, redis: Any | None = None
) -> dict[str, Any]:
    """Richer rescue operations dashboard for the Rescue Admin portal."""
    cache_key = "cache:dashboard:rescue:operations"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    active_statuses = [
        RescueStatus.DISPATCHED,
        RescueStatus.LOCATED,
        RescueStatus.RESCUED,
    ]

    status_res = await session.execute(
        select(RescueRequest.status, func.count())
        .where(RescueRequest.deleted_at.is_(None))
        .group_by(RescueRequest.status)
    )
    severity_res = await session.execute(
        select(RescueRequest.severity, func.count())
        .where(RescueRequest.deleted_at.is_(None))
        .group_by(RescueRequest.severity)
    )
    active_disp_res = await session.execute(
        select(func.count(RescueDispatch.id))
        .join(RescueRequest, RescueRequest.id == RescueDispatch.rescue_request_id)
        .where(
            RescueRequest.status.in_(active_statuses),
            RescueRequest.deleted_at.is_(None),
        )
    )
    agents_busy_res = await session.execute(
        select(func.count(func.distinct(RescueDispatchAgent.agent_id)))
        .join(RescueDispatch, RescueDispatch.id == RescueDispatchAgent.dispatch_id)
        .join(RescueRequest, RescueRequest.id == RescueDispatch.rescue_request_id)
        .where(
            RescueRequest.status.in_(active_statuses),
            RescueRequest.deleted_at.is_(None),
        )
    )
    agents_total_res = await session.execute(
        select(func.count(func.distinct(User.id)))
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            Role.name == "rescue_agent",
        )
    )
    veh_assigned_res = await session.execute(
        select(func.count(func.distinct(RescueDispatch.assigned_vehicle_id)))
        .join(RescueRequest, RescueRequest.id == RescueDispatch.rescue_request_id)
        .where(
            RescueDispatch.assigned_vehicle_id.isnot(None),
            RescueRequest.status.in_(active_statuses),
            RescueRequest.deleted_at.is_(None),
        )
    )
    veh_total_res = await session.execute(
        select(func.count(Vehicle.id)).where(Vehicle.deleted_at.is_(None))
    )

    by_status: dict[str, int] = {str(row[0]): row[1] for row in status_res.all()}
    by_severity: dict[str, int] = {str(row[0]): row[1] for row in severity_res.all()}
    active_dispatches = active_disp_res.scalar_one()
    agents_busy = agents_busy_res.scalar_one()
    agents_total = agents_total_res.scalar_one()
    agents_available = max(agents_total - agents_busy, 0)
    vehicles_assigned = veh_assigned_res.scalar_one()
    vehicles_total = veh_total_res.scalar_one()
    vehicles_available = max(vehicles_total - vehicles_assigned, 0)

    result = {
        "total_calls": sum(by_status.values()),
        "pending": by_status.get("reported", 0),
        "verified": by_status.get("verified", 0),
        "dispatched": by_status.get("dispatched", 0),
        "in_progress": by_status.get("located", 0) + by_status.get("rescued", 0),
        "admitted": by_status.get("admitted", 0),
        "rejected": by_status.get("rejected", 0),
        "by_status": by_status,
        "by_severity": by_severity,
        "active_dispatches": active_dispatches,
        "agents_available": agents_available,
        "agents_busy": agents_busy,
        "vehicles_available": vehicles_available,
        "vehicles_assigned": vehicles_assigned,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def shelter_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:shelter"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    stmt = text("""
        SELECT
            (SELECT COUNT(*) FROM shelter_facilities WHERE deleted_at IS NULL) AS total_facilities,
            (SELECT COUNT(*) FROM dog_profiles WHERE deleted_at IS NULL) AS total_dogs,
            (SELECT COUNT(*) FROM dog_profiles WHERE status = 'shelter' AND deleted_at IS NULL) AS adoptable_dogs,
            (SELECT COUNT(*) FROM kennels) AS total_kennels,
            (SELECT COUNT(*) FROM facility_transfers WHERE status = 'pending') AS pending_transfers,
            (SELECT COUNT(*) FROM dog_profiles d JOIN shelter_sections s ON d.section_id = s.id WHERE s.section_type = 'isolation' AND d.deleted_at IS NULL) AS isolation_count,
            (SELECT COUNT(*) FROM kennels WHERE sanitation_state = 'needs_cleaning') AS pending_cleaning
    """)
    row = (await session.execute(stmt)).one()

    total_dogs = row.total_dogs
    total_kennels = row.total_kennels
    result = {
        "total_facilities": row.total_facilities,
        "total_dogs": total_dogs,
        "adoptable_dogs": row.adoptable_dogs,
        "total_kennels": total_kennels,
        "occupancy_rate": (round(total_dogs / total_kennels * 100, 1) if total_kennels > 0 else 0),
        "pending_transfers": row.pending_transfers,
        "isolation_count": row.isolation_count,
        "pending_cleaning": row.pending_cleaning,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def medical_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:medical"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    recent = _ts_range(30)
    exams = await session.execute(
        select(func.count(ClinicalExam.id)).where(ClinicalExam.exam_date >= recent)
    )
    treatments = await session.execute(
        select(func.count(MedicalTreatment.id)).where(MedicalTreatment.treatment_date >= recent)
    )
    result = {
        "exams_last_30d": exams.scalar_one(),
        "treatments_last_30d": treatments.scalar_one(),
    }
    await _set_cache(redis, cache_key, result)
    return result


async def adoption_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:adoption"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    stmt = text("""
        SELECT
            (SELECT COUNT(*) FROM adoption_applications) AS total,
            (SELECT COUNT(*) FROM adoption_applications WHERE status = 'submitted') AS pending,
            (SELECT COUNT(*) FROM adoption_applications WHERE status = 'approved') AS approved,
            (SELECT COUNT(*) FROM adoption_applications WHERE status = 'completed') AS completed,
            (SELECT COUNT(*) FROM adoption_applications WHERE status = 'screening') AS screening,
            (SELECT COUNT(*) FROM adoption_applications WHERE status = 'interview') AS interview,
            (SELECT COUNT(*) FROM adoption_applications WHERE status = 'home_check') AS home_check,
            (SELECT COUNT(*) FROM adoption_applications WHERE status = 'rejected') AS rejected,
            (SELECT COUNT(*) FROM adoption_applications WHERE home_inspection_scheduled_at IS NOT NULL AND status = 'home_check') AS scheduled_home_visits,
            (SELECT COUNT(*) FROM dog_profiles WHERE is_adoptable = true AND deleted_at IS NULL) AS adoptable_dogs,
            (SELECT COUNT(*) FROM adoption_follow_ups WHERE status = 'overdue') AS overdue_follow_ups
    """)
    row = (await session.execute(stmt)).one()

    result = {
        "total_applications": row.total,
        "pending": row.pending,
        "pending_applications": row.pending,
        "approved": row.approved,
        "completed": row.completed,
        "completed_adoptions": row.completed,
        "screening": row.screening,
        "interview": row.interview,
        "home_check": row.home_check,
        "rejected": row.rejected,
        "scheduled_home_visits": row.scheduled_home_visits,
        "adoptable_dogs": row.adoptable_dogs,
        "overdue_follow_ups": row.overdue_follow_ups,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def foster_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:foster"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    stmt = text("""
        SELECT
            (SELECT COUNT(*) FROM foster_placements) AS total,
            (SELECT COUNT(*) FROM foster_placements WHERE is_active = true) AS active
    """)
    row = (await session.execute(stmt)).one()

    result = {
        "total_placements": row.total,
        "active_placements": row.active,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def volunteer_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:volunteer"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    stmt = text("""
        SELECT
            (SELECT COUNT(*) FROM volunteer_profiles) AS total,
            (SELECT COUNT(*) FROM volunteer_profiles WHERE status = 'active') AS available
    """)
    row = (await session.execute(stmt)).one()

    result = {
        "total_volunteers": row.total,
        "available": row.available,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def inventory_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:inventory"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    items = await session.execute(
        select(
            InventoryItem.category,
            func.count(InventoryItem.id),
            func.sum(InventoryItem.quantity),
        )
        .where(InventoryItem.deleted_at.is_(None))
        .group_by(InventoryItem.category)
    )
    low_stock = await session.execute(
        select(InventoryItem).where(
            InventoryItem.quantity <= InventoryItem.reorder_threshold,
            InventoryItem.deleted_at.is_(None),
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


async def finance_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:finance"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    stmt = text("""
        SELECT
            COALESCE(SUM(CASE WHEN transaction_type = 'income' AND status IN ('posted', 'reconciled') AND deleted_at IS NULL THEN amount ELSE 0 END), 0) AS income,
            COALESCE(SUM(CASE WHEN transaction_type = 'reconciliation' AND status IN ('posted', 'reconciled') AND deleted_at IS NULL THEN amount ELSE 0 END), 0) AS donation_income,
            COALESCE(SUM(CASE WHEN transaction_type = 'expense' AND status IN ('posted', 'reconciled') AND deleted_at IS NULL THEN amount ELSE 0 END), 0) AS expense,
            COUNT(CASE WHEN status = 'pending' AND deleted_at IS NULL THEN 1 END) AS pending_tx
        FROM financial_transactions
    """)
    row = (await session.execute(stmt)).one()

    unreconciled_stmt = text("""
        SELECT COALESCE(SUM(amount), 0) AS amount
        FROM donations
        WHERE status = 'success'
          AND id NOT IN (
              SELECT donation_id FROM financial_transactions WHERE donation_id IS NOT NULL AND status = 'reconciled'
          )
    """)
    unreconciled_row = (await session.execute(unreconciled_stmt)).one()

    total_income = float(row.income) + float(row.donation_income) + float(unreconciled_row.amount)
    total_expenses = float(row.expense)
    result = {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_balance": total_income - total_expenses,
        "pending_transactions": row.pending_tx,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def donor_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
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
        select(Donation)
        .where(
            Donation.created_at >= recent,
            Donation.status == DonationStatus.SUCCESS,
        )
        .order_by(Donation.created_at.desc())
        .limit(10)
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


async def staff_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:staff"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    stmt = text("""
        SELECT
            (SELECT COUNT(*) FROM users) AS total_staff,
            (SELECT COUNT(*) FROM grievance_tickets WHERE status = 'open') AS open_grievances
    """)
    row = (await session.execute(stmt)).one()

    result = {
        "total_staff": row.total_staff,
        "open_grievances": row.open_grievances,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def executive_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
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


async def public_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
    cache_key = "cache:dashboard:public"
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached

    stmt = text("""
        SELECT
            (SELECT COUNT(*) FROM dog_profiles WHERE status = 'shelter') AS adoptable_dogs,
            (SELECT COUNT(*) FROM rescue_requests WHERE status = 'rescued') AS dogs_rescued
    """)
    row = (await session.execute(stmt)).one()

    result = {
        "adoptable_dogs": row.adoptable_dogs,
        "dogs_rescued": row.dogs_rescued,
    }
    await _set_cache(redis, cache_key, result)
    return result


async def operations_dashboard(session: AsyncSession, redis: Any | None = None) -> dict[str, Any]:
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
