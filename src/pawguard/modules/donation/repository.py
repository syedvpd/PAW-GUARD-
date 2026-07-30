"""Data access for the Donation Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.donation.models import Donation, DonationStatus, DonorProfile


class DonationRepository:
    DONATION_SEARCH_FIELDS = ("transaction_id", "notes", "donor_id")
    DONATION_SORTABLE_FIELDS = {
        "amount", "currency", "donation_type", "status", "created_at", "updated_at",
    }
    DONOR_SEARCH_FIELDS = ("notes", "tax_identifier")
    DONOR_SORTABLE_FIELDS = {
        "created_at", "updated_at",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_donor_profile(self, profile: DonorProfile) -> DonorProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def get_donor_by_id(self, donor_id: uuid.UUID) -> DonorProfile | None:
        stmt = (
            select(DonorProfile)
            .options(selectinload(DonorProfile.user))
            .where(DonorProfile.id == donor_id, DonorProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_donor_by_user_id(self, user_id: uuid.UUID) -> DonorProfile | None:
        stmt = (
            select(DonorProfile)
            .options(selectinload(DonorProfile.user))
            .where(DonorProfile.user_id == user_id, DonorProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def update_donor_profile(self, donor_id: uuid.UUID, **kwargs: Any) -> DonorProfile | None:
        stmt = (
            update(DonorProfile)
            .where(DonorProfile.id == donor_id, DonorProfile.deleted_at.is_(None))
            .values(**kwargs)
            .returning(DonorProfile)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def soft_delete_donor(self, donor_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime
        stmt = (
            update(DonorProfile)
            .where(DonorProfile.id == donor_id, DonorProfile.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]

    async def create_donation(self, donation: Donation) -> Donation:
        self._session.add(donation)
        await self._session.flush()
        return donation

    async def get_donation_by_id(self, donation_id: uuid.UUID) -> Donation | None:
        stmt = (
            select(Donation)
            .options(selectinload(Donation.donor), selectinload(Donation.dog))
            .where(Donation.id == donation_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_donation_by_gateway_order_id(self, gateway_order_id: str) -> Donation | None:
        stmt = (
            select(Donation)
            .options(selectinload(Donation.donor), selectinload(Donation.dog))
            .where(Donation.gateway_order_id == gateway_order_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_donations_by_donor(self, donor_id: uuid.UUID) -> Sequence[Donation]:
        stmt = (
            select(Donation)
            .options(selectinload(Donation.dog))
            .where(Donation.donor_id == donor_id)
            .order_by(Donation.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def paginate_donations(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        donation_type: str | None = None,
        status: DonationStatus | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[Sequence[Donation], int]:
        stmt = (
            select(Donation)
            .options(selectinload(Donation.donor), selectinload(Donation.dog))
        )

        search_filter = build_search_filter(Donation, search_term, self.DONATION_SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if donation_type is not None:
            stmt = stmt.where(Donation.donation_type == donation_type)
        if status is not None:
            stmt = stmt.where(Donation.status == status)
        if date_from is not None:
            stmt = stmt.where(Donation.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Donation.created_at <= date_to)

        stmt = apply_sorting(stmt, sort, self.DONATION_SORTABLE_FIELDS)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def paginate_donors(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
    ) -> tuple[Sequence[DonorProfile], int]:
        stmt = (
            select(DonorProfile)
            .options(selectinload(DonorProfile.user))
            .where(DonorProfile.deleted_at.is_(None))
        )

        search_filter = build_search_filter(DonorProfile, search_term, self.DONOR_SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        stmt = apply_sorting(stmt, sort, self.DONOR_SORTABLE_FIELDS)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def update_donation_status(
        self, donation_id: uuid.UUID, status: DonationStatus
    ) -> Donation | None:
        stmt = (
            update(Donation)
            .where(Donation.id == donation_id)
            .values(status=status)
            .returning(Donation)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_gateway_fields(self, donation_id: uuid.UUID, **kwargs: Any) -> Donation | None:
        stmt = (
            update(Donation)
            .where(Donation.id == donation_id)
            .values(**kwargs)
            .returning(Donation)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_donations_by_ids(self, ids: list[uuid.UUID]) -> Sequence[Donation]:
        stmt = select(Donation).where(Donation.id.in_(ids))
        return (await self._session.execute(stmt)).scalars().all()

    async def list_donors_by_ids(self, ids: list[uuid.UUID]) -> Sequence[DonorProfile]:
        stmt = (
            select(DonorProfile)
            .where(DonorProfile.id.in_(ids), DonorProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def bulk_update_donation_status(
        self, ids: list[uuid.UUID], status: DonationStatus
    ) -> int:
        stmt = (
            update(Donation)
            .where(Donation.id.in_(ids))
            .values(status=status)
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def bulk_soft_delete_donors(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime
        stmt = (
            update(DonorProfile)
            .where(DonorProfile.id.in_(ids), DonorProfile.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]
