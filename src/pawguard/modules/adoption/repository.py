"""Data access for the Adoption Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.adoption.models import (
    AdoptionApplication,
    AdoptionFollowUp,
    AdoptionScore,
    AdoptionStatus,
    FollowUpStatus,
)
from pawguard.modules.auth.models import User


class AdoptionRepository:
    SEARCH_FIELDS = (
        "vetting_officer_notes",
        "home_inspection_notes",
        "residential_status",
    )
    SORTABLE_FIELDS = {
        "status", "created_at", "updated_at", "completed_at",
        "residential_status", "household_members_count",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, app: AdoptionApplication) -> AdoptionApplication:
        self._session.add(app)
        await self._session.flush()
        return app

    async def get_by_id(self, app_id: uuid.UUID) -> AdoptionApplication | None:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter).selectinload(User.roles)
            )
            .where(AdoptionApplication.id == app_id, AdoptionApplication.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_by_dog(self, dog_id: uuid.UUID) -> Sequence[AdoptionApplication]:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter).selectinload(User.roles)
            )
            .where(AdoptionApplication.dog_id == dog_id, AdoptionApplication.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_by_adopter(self, adopter_id: uuid.UUID) -> Sequence[AdoptionApplication]:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter).selectinload(User.roles)
            )
            .where(
                AdoptionApplication.adopter_id == adopter_id,
                AdoptionApplication.deleted_at.is_(None),
            )
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: AdoptionStatus | None = None,
        dog_id: uuid.UUID | None = None,
        adopter_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[AdoptionApplication], int]:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter).selectinload(User.roles)
            )
            .where(AdoptionApplication.deleted_at.is_(None))
        )

        search_filter = build_search_filter(AdoptionApplication, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if status is not None:
            stmt = stmt.where(AdoptionApplication.status == status)
        if dog_id is not None:
            stmt = stmt.where(AdoptionApplication.dog_id == dog_id)
        if adopter_id is not None:
            stmt = stmt.where(AdoptionApplication.adopter_id == adopter_id)

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_by_ids(self, ids: list[uuid.UUID]) -> Sequence[AdoptionApplication]:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter).selectinload(User.roles)
            )
            .where(AdoptionApplication.id.in_(ids), AdoptionApplication.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def bulk_soft_delete(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        from sqlalchemy import update
        stmt = (
            update(AdoptionApplication)
            .where(AdoptionApplication.id.in_(ids), AdoptionApplication.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    # Statuses that exclusively lock a dog against other applications. Per the
    # PRR, exclusivity starts once an application reaches home-inspection
    # approval (HOME_CHECK), not just final APPROVED - two applicants must
    # not both be mid-inspection for the same dog at once.
    LOCKING_STATUSES = (
        AdoptionStatus.HOME_CHECK, AdoptionStatus.APPROVED, AdoptionStatus.COMPLETED,
    )

    async def get_approved_application_for_dog(
        self, dog_id: uuid.UUID
    ) -> AdoptionApplication | None:
        stmt = (
            select(AdoptionApplication)
            .where(
                AdoptionApplication.dog_id == dog_id,
                AdoptionApplication.status.in_(self.LOCKING_STATUSES),
                AdoptionApplication.deleted_at.is_(None)
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_application_by_adopter_and_dog(
        self, adopter_id: uuid.UUID, dog_id: uuid.UUID
    ) -> AdoptionApplication | None:
        stmt = (
            select(AdoptionApplication)
            .where(
                AdoptionApplication.adopter_id == adopter_id,
                AdoptionApplication.dog_id == dog_id,
                AdoptionApplication.status != AdoptionStatus.REJECTED,
                AdoptionApplication.deleted_at.is_(None),
            )
            .order_by(AdoptionApplication.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def bulk_update_status(self, ids: list[uuid.UUID], status: AdoptionStatus) -> int:
        from sqlalchemy import update
        stmt = (
            update(AdoptionApplication)
            .where(AdoptionApplication.id.in_(ids), AdoptionApplication.deleted_at.is_(None))
            .values(status=status)
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def get_by_ids(self, ids: list[uuid.UUID]) -> Sequence[AdoptionApplication]:
        """Bulk-fetch non-deleted applications by id, preserving input order."""
        if not ids:
            return []
        stmt = select(AdoptionApplication).where(
            AdoptionApplication.id.in_(ids),
            AdoptionApplication.deleted_at.is_(None),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        index = {row.id: row for row in rows}
        return [index[i] for i in ids if i in index]

    async def create_score(self, score: AdoptionScore) -> AdoptionScore:
        self._session.add(score)
        await self._session.flush()
        return score

    async def get_scores_for_application(self, app_id: uuid.UUID) -> Sequence[AdoptionScore]:
        stmt = (
            select(AdoptionScore)
            .where(AdoptionScore.application_id == app_id)
            .order_by(AdoptionScore.scored_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_latest_score_for_application(self, app_id: uuid.UUID) -> AdoptionScore | None:
        stmt = (
            select(AdoptionScore)
            .where(AdoptionScore.application_id == app_id)
            .order_by(AdoptionScore.scored_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_completed_applications(self) -> Sequence[AdoptionApplication]:
        stmt = (
            select(AdoptionApplication)
            .where(
                AdoptionApplication.status == AdoptionStatus.COMPLETED,
                AdoptionApplication.deleted_at.is_(None),
            )
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_follow_up_by_id(self, follow_up_id: uuid.UUID) -> AdoptionFollowUp | None:
        stmt = (
            select(AdoptionFollowUp)
            .options(selectinload(AdoptionFollowUp.application))
            .where(AdoptionFollowUp.id == follow_up_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_follow_ups_for_application(
        self, app_id: uuid.UUID
    ) -> Sequence[AdoptionFollowUp]:
        stmt = (
            select(AdoptionFollowUp)
            .options(selectinload(AdoptionFollowUp.application))
            .where(AdoptionFollowUp.adoption_application_id == app_id)
            .order_by(AdoptionFollowUp.due_day)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_follow_up_for_milestone(
        self, app_id: uuid.UUID, due_day: int
    ) -> AdoptionFollowUp | None:
        stmt = (
            select(AdoptionFollowUp)
            .where(
                AdoptionFollowUp.adoption_application_id == app_id,
                AdoptionFollowUp.due_day == due_day,
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_due_follow_ups(self, now: datetime) -> Sequence[AdoptionFollowUp]:
        """Follow-ups that are due (or overdue) and not yet submitted.

        Joins the parent application so callers never have to chase the
        adopter through a lazy load.
        """
        stmt = (
            select(AdoptionFollowUp)
            .options(selectinload(AdoptionFollowUp.application))
            .join(
                AdoptionApplication,
                AdoptionApplication.id == AdoptionFollowUp.adoption_application_id,
            )
            .where(
                AdoptionFollowUp.status.in_(
                    [FollowUpStatus.PENDING, FollowUpStatus.OVERDUE]
                ),
                AdoptionFollowUp.due_at <= now,
                AdoptionApplication.deleted_at.is_(None),
            )
            .order_by(AdoptionFollowUp.due_at)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_follow_up(self, follow_up: AdoptionFollowUp) -> AdoptionFollowUp:
        self._session.add(follow_up)
        await self._session.flush()
        return follow_up
