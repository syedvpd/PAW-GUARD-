"""Data access for the Donation Management module.

Repositories never contain business decisions (RULE-002).
"""

import calendar
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from datetime import date as date_type
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.auth.models import Role, User
from pawguard.modules.donation.models import (
    CampaignStatus,
    DogSponsorship,
    Donation,
    DonationCampaign,
    DonationStatus,
    DonorProfile,
    RecurringStatus,
    RecurringSubscription,
    SponsorshipStatus,
)


class DonationRepository:
    DONATION_SEARCH_FIELDS = ("transaction_id", "notes", "donor_id")
    DONATION_SORTABLE_FIELDS = {
        "amount", "currency", "donation_type", "status", "created_at", "updated_at",
    }
    DONOR_SEARCH_FIELDS = ("notes", "tax_identifier")
    DONOR_SORTABLE_FIELDS = {
        "created_at", "updated_at",
    }
    CAMPAIGN_SEARCH_FIELDS = ("name", "description")
    CAMPAIGN_SORTABLE_FIELDS = {
        "target_amount", "currency", "campaign_type", "status",
        "start_date", "end_date", "created_at",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_donor_profile(self, profile: DonorProfile) -> DonorProfile:
        self._session.add(profile)
        await self._session.flush()
        await self._session.refresh(profile)
        return profile

    async def get_donor_by_id(self, donor_id: uuid.UUID) -> DonorProfile | None:
        stmt = (
            select(DonorProfile)
            .options(
                selectinload(DonorProfile.user)
                .selectinload(User.roles)
                .selectinload(Role.permissions)
            )
            .where(DonorProfile.id == donor_id, DonorProfile.deleted_at.is_(None))
            .execution_options(populate_existing=True)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_donor_by_user_id(self, user_id: uuid.UUID) -> DonorProfile | None:
        stmt = (
            select(DonorProfile)
            .options(
                selectinload(DonorProfile.user)
                .selectinload(User.roles)
                .selectinload(Role.permissions)
            )
            .where(DonorProfile.user_id == user_id, DonorProfile.deleted_at.is_(None))
            .execution_options(populate_existing=True)
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
        from datetime import datetime
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
        date_from: date_type | None = None,
        date_to: date_type | None = None,
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
            .options(selectinload(DonorProfile.user).selectinload(User.roles))
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
        current = await self.get_donation_by_id(donation_id)
        if current is None:
            return None

        old_status = current.status
        sponsorship_id = current.sponsorship_id

        stmt = (
            update(Donation)
            .where(Donation.id == donation_id)
            .values(**kwargs)
            .returning(Donation)
        )
        result = await self._session.execute(stmt)
        updated = result.scalar_one_or_none()

        if (
            updated
            and updated.status == DonationStatus.SUCCESS
            and old_status != DonationStatus.SUCCESS
            and sponsorship_id
        ):
            from pawguard.modules.donation.models import DogSponsorship

            sp = await self._session.get(DogSponsorship, sponsorship_id)
            if sp and sp.next_charge_date:
                month = sp.next_charge_date.month + 1
                year = sp.next_charge_date.year
                if month > 12:
                    month = 1
                    year += 1
                day = min(sp.next_charge_date.day, calendar.monthrange(year, month)[1])
                next_date = sp.next_charge_date.replace(year=year, month=month, day=day)
                sp.next_charge_date = next_date

        return updated

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
        from datetime import datetime
        stmt = (
            update(DonorProfile)
            .where(DonorProfile.id.in_(ids), DonorProfile.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def create_sponsorship(self, sponsorship: DogSponsorship) -> DogSponsorship:
        self._session.add(sponsorship)
        await self._session.flush()
        refreshed = await self.get_sponsorship_by_id(sponsorship.id)
        return refreshed if refreshed is not None else sponsorship

    async def update_sponsorship_status(
        self, sponsorship_id: uuid.UUID, status: SponsorshipStatus
    ) -> DogSponsorship | None:
        stmt = (
            update(DogSponsorship)
            .where(DogSponsorship.id == sponsorship_id)
            .values(status=status)
            .returning(DogSponsorship)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def cancel_sponsorship(
        self, sponsorship_id: uuid.UUID, cancelled_at: datetime
    ) -> DogSponsorship | None:
        stmt = (
            update(DogSponsorship)
            .where(DogSponsorship.id == sponsorship_id)
            .values(status=SponsorshipStatus.CANCELLED, cancelled_at=cancelled_at)
            .returning(DogSponsorship)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_sponsorship_by_id(self, sponsorship_id: uuid.UUID) -> DogSponsorship | None:
        stmt = (
            select(DogSponsorship)
            .options(selectinload(DogSponsorship.dog), selectinload(DogSponsorship.donor))
            .where(DogSponsorship.id == sponsorship_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_sponsorships_for_donor(self, donor_id: uuid.UUID) -> Sequence[DogSponsorship]:
        stmt = (
            select(DogSponsorship)
            .options(selectinload(DogSponsorship.dog))
            .where(DogSponsorship.donor_id == donor_id)
            .order_by(DogSponsorship.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_all_sponsorships(self) -> Sequence[DogSponsorship]:
        stmt = (
            select(DogSponsorship)
            .options(selectinload(DogSponsorship.dog), selectinload(DogSponsorship.donor))
            .order_by(DogSponsorship.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_due_sponsorships(self, as_of: date_type) -> Sequence[DogSponsorship]:
        stmt = (
            select(DogSponsorship)
            .options(selectinload(DogSponsorship.donor))
            .where(
                DogSponsorship.next_charge_date <= as_of,
                DogSponsorship.status == SponsorshipStatus.ACTIVE,
            )
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def advance_charge_date(
        self, sponsorship_id: uuid.UUID, new_date: date_type
    ) -> DogSponsorship | None:
        stmt = (
            update(DogSponsorship)
            .where(DogSponsorship.id == sponsorship_id)
            .values(next_charge_date=new_date)
            .returning(DogSponsorship)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Donation campaigns (PRR 3.1.7 / 3.11) ─────────────────────────────

    async def create_campaign(self, campaign: DonationCampaign) -> DonationCampaign:
        self._session.add(campaign)
        await self._session.flush()
        return campaign

    async def get_campaign_by_id(
        self, campaign_id: uuid.UUID, *, include_deleted: bool = False
    ) -> DonationCampaign | None:
        stmt = select(DonationCampaign).where(DonationCampaign.id == campaign_id)
        if not include_deleted:
            stmt = stmt.where(DonationCampaign.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def update_campaign(
        self, campaign_id: uuid.UUID, **kwargs: Any
    ) -> DonationCampaign | None:
        stmt = (
            update(DonationCampaign)
            .where(
                DonationCampaign.id == campaign_id,
                DonationCampaign.deleted_at.is_(None),
            )
            .values(**kwargs)
            .returning(DonationCampaign)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def soft_delete_campaign(self, campaign_id: uuid.UUID) -> bool:
        stmt = (
            update(DonationCampaign)
            .where(
                DonationCampaign.id == campaign_id,
                DonationCampaign.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]

    async def paginate_campaigns(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: CampaignStatus | None = None,
        campaign_type: str | None = None,
    ) -> tuple[Sequence[DonationCampaign], int]:
        stmt = select(DonationCampaign).where(DonationCampaign.deleted_at.is_(None))

        search_filter = build_search_filter(
            DonationCampaign, search_term, self.CAMPAIGN_SEARCH_FIELDS
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        if status is not None:
            stmt = stmt.where(DonationCampaign.status == status)
        if campaign_type is not None:
            stmt = stmt.where(DonationCampaign.campaign_type == campaign_type)

        stmt = apply_sorting(stmt, sort, self.CAMPAIGN_SORTABLE_FIELDS)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_active_campaigns(self, as_of: date_type) -> Sequence[DonationCampaign]:
        stmt = (
            select(DonationCampaign)
            .where(
                DonationCampaign.status == CampaignStatus.ACTIVE,
                DonationCampaign.deleted_at.is_(None),
                DonationCampaign.start_date <= as_of,
            )
            .order_by(DonationCampaign.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_campaign_totals(
        self, campaign_id: uuid.UUID
    ) -> tuple[float, int]:
        """Raised amount and distinct donor count for a campaign (successful
        donations only)."""
        raised, donor_count = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(Donation.amount), 0),
                    func.count(func.distinct(Donation.donor_id)),
                ).where(
                    Donation.campaign_id == campaign_id,
                    Donation.status == DonationStatus.SUCCESS,
                )
            )
        ).one()
        return float(raised), int(donor_count)

    async def has_pending_donation_for_sponsorship(self, sponsorship_id: uuid.UUID) -> bool:
        stmt = select(Donation).where(
            Donation.sponsorship_id == sponsorship_id,
            Donation.status == DonationStatus.PENDING,
        )
        res = (await self._session.execute(stmt)).scalars().first()
        return res is not None

    # ── Recurring subscriptions ──────────────────────────────────────

    async def create_recurring_subscription(
        self, subscription: RecurringSubscription
    ) -> RecurringSubscription:
        self._session.add(subscription)
        await self._session.flush()
        return subscription

    async def get_recurring_subscription_by_id(
        self, subscription_id: uuid.UUID
    ) -> RecurringSubscription | None:
        stmt = select(RecurringSubscription).where(
            RecurringSubscription.id == subscription_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def cancel_recurring_subscription(
        self, subscription_id: uuid.UUID, cancelled_at: datetime
    ) -> RecurringSubscription | None:
        stmt = (
            update(RecurringSubscription)
            .where(RecurringSubscription.id == subscription_id)
            .values(
                status=RecurringStatus.CANCELLED,
                cancelled_at=cancelled_at,
            )
            .returning(RecurringSubscription)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_due_recurring_subscriptions(
        self, as_of: date_type
    ) -> Sequence[RecurringSubscription]:
        stmt = (
            select(RecurringSubscription)
            .options(selectinload(RecurringSubscription.donor))
            .where(
                RecurringSubscription.next_charge_date <= as_of,
                RecurringSubscription.status == RecurringStatus.ACTIVE,
            )
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def has_pending_donation_for_subscription(
        self, subscription_id: uuid.UUID
    ) -> bool:
        stmt = select(Donation).where(
            Donation.recurring_subscription_id == subscription_id,
            Donation.status == DonationStatus.PENDING,
        )
        res = (await self._session.execute(stmt)).scalars().first()
        return res is not None

    async def advance_recurring_charge_date(
        self, subscription_id: uuid.UUID, new_date: date_type
    ) -> RecurringSubscription | None:
        stmt = (
            update(RecurringSubscription)
            .where(RecurringSubscription.id == subscription_id)
            .values(next_charge_date=new_date)
            .returning(RecurringSubscription)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recurring_subscriptions_for_donor(
        self, donor_id: uuid.UUID
    ) -> Sequence[RecurringSubscription]:
        stmt = (
            select(RecurringSubscription)
            .where(RecurringSubscription.donor_id == donor_id)
            .order_by(RecurringSubscription.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()
