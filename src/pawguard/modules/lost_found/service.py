"""LostFoundService: owns lost/found registers and reunifying cross-matching logic (RULE-003)."""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pawguard.core.exceptions import ForbiddenError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.lost_found.models import (
    FoundReport,
    LostReport,
    MatchStatus,
    ReportMatch,
    ReportStatus,
    Species,
)
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.lost_found.schemas import (
    FoundReportCreate,
    FoundReportResponse,
    LostReportCreate,
    LostReportResponse,
    OwnershipClaimReview,
    OwnershipClaimSubmit,
    ReportMatchResponse,
)
from pawguard.services.audit_service import AuditService


class LostFoundService:
    def __init__(
        self, repository: LostFoundRepository, audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service

    async def report_lost_pet(
        self, user_id: uuid.UUID, payload: LostReportCreate,
        actor_id: uuid.UUID | None = None, ip_address: str | None = None,
    ) -> LostReport:
        report = LostReport(
            user_id=user_id,
            pet_name=payload.pet_name,
            breed=payload.breed.lower(),
            color=payload.color.lower(),
            microchip_id=payload.microchip_id,
            location_address=payload.location_address,
            latitude=payload.latitude,
            longitude=payload.longitude,
            lost_at=payload.lost_at,
            status=ReportStatus.ACTIVE,
            photo_url=payload.photo_url,
        )
        await self._repo.create_lost_report(report)
        await self._repo._session.flush()
        await self._run_matching_for_lost(report)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_REPORTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"report_id": str(report.id), "type": "lost"},
            )
        return report

    async def report_found_pet(
        self, user_id: uuid.UUID, payload: FoundReportCreate,
        actor_id: uuid.UUID | None = None, ip_address: str | None = None,
    ) -> FoundReport:
        report = FoundReport(
            user_id=user_id,
            breed_observed=payload.breed_observed.lower(),
            color_observed=payload.color_observed.lower(),
            location_address=payload.location_address,
            latitude=payload.latitude,
            longitude=payload.longitude,
            found_at=payload.found_at,
            status=ReportStatus.ACTIVE,
            photo_url=payload.photo_url,
        )
        await self._repo.create_found_report(report)
        await self._repo._session.flush()
        await self._run_matching_for_found(report)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_REPORTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"report_id": str(report.id), "type": "found"},
            )
        return report

    async def resolve_lost_report(
        self, report_id: uuid.UUID, actor_id: uuid.UUID | None = None, ip_address: str | None = None
    ) -> LostReport:
        report = await self._repo.get_lost_report_by_id(report_id)
        if report is None:
            raise NotFoundError("Lost report not found.")
        report.status = ReportStatus.RESOLVED
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_RESOLVED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"report_id": str(report_id), "type": "lost"},
            )
        return report

    async def resolve_found_report(
        self, report_id: uuid.UUID, actor_id: uuid.UUID | None = None, ip_address: str | None = None
    ) -> FoundReport:
        report = await self._repo.get_found_report_by_id(report_id)
        if report is None:
            raise NotFoundError("Found report not found.")
        report.status = ReportStatus.RESOLVED
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_RESOLVED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"report_id": str(report_id), "type": "found"},
            )
        return report

    async def get_matches_for_lost(self, report_id: uuid.UUID) -> Sequence[ReportMatch]:
        return await self._repo.list_matches_for_lost_report(report_id)

    async def get_matches_for_found(self, report_id: uuid.UUID) -> Sequence[ReportMatch]:
        return await self._repo.list_matches_for_found_report(report_id)

    async def list_lost_reports_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: ReportStatus | None = None,
        species: Species | None = None,
    ) -> PaginatedResponse[LostReportResponse]:
        reports, total = await self._repo.list_lost_reports_paginated(
            page_params, sort, search_term=search_term, status=status, species=species,
        )
        return PaginatedResponse(
            data=list(reports),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def list_found_reports_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: ReportStatus | None = None,
        species: Species | None = None,
    ) -> PaginatedResponse[FoundReportResponse]:
        reports, total = await self._repo.list_found_reports_paginated(
            page_params, sort, search_term=search_term, status=status, species=species,
        )
        return PaginatedResponse(
            data=list(reports),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def list_matches_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        lost_report_id: uuid.UUID | None = None,
        found_report_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[ReportMatchResponse]:
        matches, total = await self._repo.list_matches_paginated(
            page_params, sort, lost_report_id=lost_report_id, found_report_id=found_report_id,
        )
        return PaginatedResponse(
            data=list(matches),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def soft_delete_lost_report(
        self, report_id: uuid.UUID, actor_id: uuid.UUID | None = None, ip_address: str | None = None
    ) -> None:
        deleted = await self._repo.soft_delete_lost_report(report_id)
        if not deleted:
            raise NotFoundError("Lost report not found.")
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"report_id": str(report_id), "type": "lost"},
            )

    async def soft_delete_found_report(
        self, report_id: uuid.UUID, actor_id: uuid.UUID | None = None, ip_address: str | None = None
    ) -> None:
        deleted = await self._repo.soft_delete_found_report(report_id)
        if not deleted:
            raise NotFoundError("Found report not found.")
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"report_id": str(report_id), "type": "found"},
            )

    async def bulk_delete_lost_reports(
        self, ids: list[uuid.UUID], actor_id: uuid.UUID | None = None, ip_address: str | None = None
    ) -> int:
        count = await self._repo.bulk_delete_lost_reports(ids)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"report_ids": [str(i) for i in ids], "count": count, "type": "lost"},
            )
        return count

    async def bulk_delete_found_reports(
        self, ids: list[uuid.UUID], actor_id: uuid.UUID | None = None, ip_address: str | None = None
    ) -> int:
        count = await self._repo.bulk_delete_found_reports(ids)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"report_ids": [str(i) for i in ids], "count": count, "type": "found"},
            )
        return count

    async def update_match_status(self, match_id: uuid.UUID, status: MatchStatus) -> ReportMatch:
        match = await self._repo.get_match_by_id(match_id)
        if match is None:
            raise NotFoundError("Report match record not found.")
        match.status = status
        return match

    async def get_match(self, match_id: uuid.UUID) -> ReportMatch:
        match = await self._repo.get_match_by_id(match_id)
        if match is None:
            raise NotFoundError("Report match record not found.")
        return match

    # --- Ownership-Verification Claim Workflow (PRR 3.10) -----------------

    async def submit_ownership_claim(
        self,
        match_id: uuid.UUID,
        claimant_user_id: uuid.UUID,
        payload: OwnershipClaimSubmit,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ReportMatch:
        """A potential owner files a claim with supporting documents against a
        matched lost/found pair. Only the reporters of either side of the match
        may claim it (PRR 3.10 ownership verification)."""
        match = await self._repo.get_match_by_id(match_id)
        if match is None:
            raise NotFoundError("Report match record not found.")

        is_lost_owner = (
            match.lost_report is not None
            and match.lost_report.user_id == claimant_user_id
        )
        is_found_reporter = (
            match.found_report is not None
            and match.found_report.user_id == claimant_user_id
        )
        if not is_lost_owner and not is_found_reporter:
            raise ForbiddenError(
                "Only a reporter on this match may submit an ownership claim."
            )

        if match.status != MatchStatus.PENDING:
            raise ValidationFailedError(
                "This match has already been reviewed; claims are closed."
            )
        if not (payload.microchip_doc_url or payload.vet_bill_url or payload.photo_proof_url):
            raise ValidationFailedError(
                "At least one proof document is required to verify ownership."
            )

        match.microchip_doc_url = payload.microchip_doc_url
        match.vet_bill_url = payload.vet_bill_url
        match.photo_proof_url = payload.photo_proof_url
        match.verification_notes = payload.verification_notes
        match.claim_submitted_at = datetime.now(UTC)
        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_CLAIM_SUBMITTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "match_id": str(match.id),
                    "lost_report_id": str(match.lost_report_id),
                    "found_report_id": str(match.found_report_id),
                    "claimant_user_id": str(claimant_user_id),
                    "proof_types": [
                        doc for doc in (
                            "microchip_doc" if payload.microchip_doc_url else None,
                            "vet_bill" if payload.vet_bill_url else None,
                            "photo_proof" if payload.photo_proof_url else None,
                        ) if doc
                    ],
                },
            )
        return match

    async def review_ownership_claim(
        self,
        match_id: uuid.UUID,
        payload: OwnershipClaimReview,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ReportMatch:
        """Staff reviews a submitted claim: approve -> confirm the match and
        resolve both reports; reject -> mark the match rejected. The reviewer
        and review time are recorded for the audit trail (PRR 3.10)."""
        match = await self._repo.get_match_by_id(match_id)
        if match is None:
            raise NotFoundError("Report match record not found.")
        if match.claim_submitted_at is None:
            raise ValidationFailedError(
                "No ownership claim has been submitted for this match yet."
            )
        if match.status != MatchStatus.PENDING:
            raise ValidationFailedError(
                "This match has already been reviewed."
            )

        now = datetime.now(UTC)
        new_status = MatchStatus.CONFIRMED if payload.approve else MatchStatus.REJECTED
        match.status = new_status
        match.claim_reviewed_at = now
        match.claim_reviewed_by = actor_id
        if payload.verification_notes:
            match.verification_notes = payload.verification_notes
        await self._repo._session.flush()

        if payload.approve:
            await self.resolve_lost_report(
                match.lost_report_id, actor_id=actor_id, ip_address=ip_address,
            )
            await self.resolve_found_report(
                match.found_report_id, actor_id=actor_id, ip_address=ip_address,
            )

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_CLAIM_REVIEWED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "match_id": str(match.id),
                    "new_status": new_status.value,
                    "reviewed_by": str(actor_id),
                    "reviewed_at": now.isoformat(),
                },
            )
        return match

    # --- Algorithmic Cross-Matching Engine ---

    def _calculate_distance_km(
        self, lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None
    ) -> float:
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return 999.0  # unknown distance

        # Haversine formula
        r = 6371.0  # Earth radius in km
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (
            math.sin(d_lat / 2.0) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(d_lon / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    def _evaluate_match_score(self, lost: LostReport, found: FoundReport) -> float:
        score = 0.0

        # 1. Breed match (max 33.33)
        if lost.breed == found.breed_observed:
            score += 33.33
        elif lost.breed in found.breed_observed or found.breed_observed in lost.breed:
            score += 15.0  # partial match

        # 2. Color match (max 33.33)
        if lost.color == found.color_observed:
            score += 33.33
        elif lost.color in found.color_observed or found.color_observed in lost.color:
            score += 15.0  # partial match

        # 3. Distance Match (max 33.34)
        dist = self._calculate_distance_km(
            float(lost.latitude) if lost.latitude is not None else None,
            float(lost.longitude) if lost.longitude is not None else None,
            float(found.latitude) if found.latitude is not None else None,
            float(found.longitude) if found.longitude is not None else None,
        )
        if dist <= 2.0:
            score += 33.34
        elif dist <= 5.0:
            score += 20.0
        elif dist <= 10.0:
            score += 10.0

        return round(score, 2)

    async def _run_matching_for_lost(self, lost: LostReport) -> None:
        active_founds = await self._repo.list_found_reports(status=ReportStatus.ACTIVE)
        for found in active_founds:
            score = self._evaluate_match_score(lost, found)
            if score >= 50.0:
                match = ReportMatch(
                    lost_report_id=lost.id,
                    found_report_id=found.id,
                    confidence_score=score,
                    status=MatchStatus.PENDING,
                )
                await self._repo.create_match(match)

    async def _run_matching_for_found(self, found: FoundReport) -> None:
        active_losts = await self._repo.list_lost_reports(status=ReportStatus.ACTIVE)
        for lost in active_losts:
            score = self._evaluate_match_score(lost, found)
            if score >= 50.0:
                match = ReportMatch(
                    lost_report_id=lost.id,
                    found_report_id=found.id,
                    confidence_score=score,
                    status=MatchStatus.PENDING,
                )
                await self._repo.create_match(match)
