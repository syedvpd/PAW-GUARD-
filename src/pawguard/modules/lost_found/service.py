"""LostFoundService: owns lost/found registers and reunifying cross-matching logic (RULE-003)."""

import math
import uuid
from datetime import UTC, datetime
from typing import Sequence

from pawguard.core.exceptions import NotFoundError
from pawguard.modules.lost_found.models import FoundReport, LostReport, MatchStatus, ReportMatch, ReportStatus
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.lost_found.schemas import FoundReportCreate, LostReportCreate


class LostFoundService:
    def __init__(self, repository: LostFoundRepository) -> None:
        self._repo = repository

    async def report_lost_pet(self, user_id: uuid.UUID, payload: LostReportCreate) -> LostReport:
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

        # Run cross matching trigger
        await self._run_matching_for_lost(report)

        return report

    async def report_found_pet(self, user_id: uuid.UUID, payload: FoundReportCreate) -> FoundReport:
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

        # Run cross matching trigger
        await self._run_matching_for_found(report)

        return report

    async def resolve_lost_report(self, report_id: uuid.UUID) -> LostReport:
        report = await self._repo.get_lost_report_by_id(report_id)
        if report is None:
            raise NotFoundError("Lost report not found.")
        report.status = ReportStatus.RESOLVED
        return report

    async def resolve_found_report(self, report_id: uuid.UUID) -> FoundReport:
        report = await self._repo.get_found_report_by_id(report_id)
        if report is None:
            raise NotFoundError("Found report not found.")
        report.status = ReportStatus.RESOLVED
        return report

    async def get_matches_for_lost(self, report_id: uuid.UUID) -> Sequence[ReportMatch]:
        return await self._repo.list_matches_for_lost_report(report_id)

    async def get_matches_for_found(self, report_id: uuid.UUID) -> Sequence[ReportMatch]:
        return await self._repo.list_matches_for_found_report(report_id)

    async def update_match_status(self, match_id: uuid.UUID, status: MatchStatus) -> ReportMatch:
        match = await self._repo.get_match_by_id(match_id)
        if match is None:
            raise NotFoundError("Report match record not found.")
        match.status = status
        return match

    # --- Algorithmic Cross-Matching Engine ---

    def _calculate_distance_km(
        self, lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None
    ) -> float:
        if None in (lat1, lon1, lat2, lon2):
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
