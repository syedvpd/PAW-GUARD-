"""LostFoundService: owns lost/found registers and reunifying cross-matching logic (RULE-003)."""

import contextlib
import hashlib
import math
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from logging import getLogger
from typing import Any

from arq import ArqRedis

from pawguard.core.exceptions import ForbiddenError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.lost_found.models import (
    FoundReport,
    LostReport,
    MatchStatus,
    PetSighting,
    ReportMatch,
    ReportMedia,
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
    PetSightingCreate,
    ReportMatchResponse,
)
from pawguard.modules.notifications.schemas import BroadcastCreate, NotificationSend
from pawguard.modules.notifications.service import NotificationService
from pawguard.redis.client import RedisClient, is_null_redis
from pawguard.services.audit_service import AuditService
from pawguard.services.cache_service import CacheService

logger = getLogger(__name__)


class LostFoundService:
    def __init__(
        self,
        repository: LostFoundRepository,
        audit_service: AuditService | None = None,
        arq_pool: ArqRedis | None = None,
        notification_service: NotificationService | None = None,
        redis: RedisClient | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service
        self._arq = arq_pool
        self._notification_svc = notification_service
        self._redis = redis or arq_pool

    async def queue_lost_alert_broadcast(
        self,
        report_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        is_admin: bool = False,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        report = await self._repo.get_lost_report_by_id(report_id)
        if report is None:
            raise NotFoundError("Lost report not found.")
        if report.user_id != actor_id and not is_admin:
            raise ForbiddenError("Only the lost-pet reporter may broadcast this alert.")
        if report.status != ReportStatus.ACTIVE:
            raise ValidationFailedError("Only active lost-pet reports can be broadcast.")
        if self._arq is None:
            from pawguard.workers.jobs.lost_found_jobs import broadcast_lost_pet_alert

            await broadcast_lost_pet_alert(
                {"job_name": "broadcast_lost_pet_alert"}, report_id=str(report_id)
            )
        else:
            try:
                await self._arq.enqueue_job(
                    "broadcast_lost_pet_alert",
                    report_id=str(report_id),
                    actor_id=str(actor_id),
                    ip_address=ip_address,
                )
            except Exception as exc:
                logger.warning("arq_enqueue_failed_broadcasting_inline", error=str(exc))
                from pawguard.workers.jobs.lost_found_jobs import broadcast_lost_pet_alert

                await broadcast_lost_pet_alert(
                    {"job_name": "broadcast_lost_pet_alert"}, report_id=str(report_id)
                )
        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.LOST_FOUND_BROADCAST_QUEUED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"report_id": str(report_id)},
            )
        return {"report_id": report_id, "queued": True}

    async def report_lost_pet(
        self,
        user_id: uuid.UUID,
        payload: LostReportCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> LostReport:
        lock_token = str(uuid.uuid4())
        lock_acquired = False
        cache_svc = None
        ident_hash = ""
        if self._redis is not None and not is_null_redis(self._redis):
            ident_str = f"{user_id}:{payload.companion_pet_id}:{payload.microchip_id}:{payload.species}:{payload.pet_name.strip().lower()}:{payload.breed.strip().lower()}:{payload.location_address.strip().lower()}"
            ident_hash = hashlib.sha256(ident_str.encode()).hexdigest()[:16]
            cache_svc = CacheService(self._redis, namespace="lost_found")
            lock_acquired = await cache_svc.acquire_lock(
                f"lock:lost:{user_id}:{ident_hash}", lock_token, expire_ms=10000
            )

        try:
            # Duplicate prevention check: return existing active report if identical
            existing = await self._repo.find_active_lost_duplicate(
                user_id=user_id,
                companion_pet_id=payload.companion_pet_id,
                microchip_id=payload.microchip_id,
                species=payload.species,
                pet_name=payload.pet_name,
                breed=payload.breed,
                location_address=payload.location_address,
            )
            if existing is not None and isinstance(existing, LostReport):
                logger.info(
                    "duplicate_lost_report_prevented",
                    user_id=str(user_id),
                    existing_report_id=str(existing.id),
                )
                return existing

            from pawguard.services.storage_service import StorageService

            # Determine photo keys and video key
            photo_keys = payload.photo_object_keys
            if photo_keys is None:
                photo_keys = [payload.photo_object_key] if payload.photo_object_key else []
            video_key = payload.video_object_key

            # Validate S3 objects if present
            if photo_keys or video_key:
                StorageService().validate_report_media(photo_keys, video_key)

            # Legacy primary key to store on report model
            primary_key = photo_keys[0] if photo_keys else payload.photo_object_key
            # Resolve legacy photo url if primary key is present
            photo_url = payload.photo_url
            if primary_key:
                with contextlib.suppress(Exception):
                    photo_url = StorageService().generate_public_url(object_key=primary_key)

            report = LostReport(
                user_id=user_id,
                species=payload.species,
                pet_name=payload.pet_name,
                breed=payload.breed.lower(),
                color=payload.color.lower(),
                microchip_id=payload.microchip_id,
                collar_color=payload.collar_color,
                collar_description=payload.collar_description,
                marker_description=payload.marker_description,
                location_address=payload.location_address,
                latitude=payload.latitude,
                longitude=payload.longitude,
                lost_at=payload.lost_at,
                status=ReportStatus.ACTIVE,
                companion_pet_id=payload.companion_pet_id,
                photo_url=photo_url,
                photo_object_key=primary_key,
            )
            await self._repo.create_lost_report(report)
            await self._repo._session.flush()

            # Save ReportMedia entries
            media_items = []
            for idx, key in enumerate(photo_keys):
                media_items.append(
                    ReportMedia(
                        lost_report_id=report.id,
                        media_type="photo",
                        object_key=key,
                        is_primary=(idx == 0),
                        display_order=idx,
                    )
                )
            if video_key:
                media_items.append(
                    ReportMedia(
                        lost_report_id=report.id,
                        media_type="video",
                        object_key=video_key,
                        is_primary=False,
                        display_order=len(photo_keys),
                    )
                )

            for m in media_items:
                self._repo._session.add(m)
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
            reloaded = await self._repo.get_lost_report_by_id(report.id)
            return reloaded or report
        finally:
            if lock_acquired and cache_svc is not None:
                await cache_svc.release_lock(f"lock:lost:{user_id}:{ident_hash}", lock_token)

    async def record_public_sighting(
        self, payload: PetSightingCreate, ip_address: str | None = None
    ) -> PetSighting:
        sighting = PetSighting(
            pet_id=payload.pet_id,
            lost_report_id=payload.lost_report_id,
            finder_name=payload.finder_name,
            finder_phone=payload.finder_phone,
            finder_address=payload.finder_address,
            latitude=payload.latitude,
            longitude=payload.longitude,
            location_address=payload.location_address,
            message=payload.message,
        )
        await self._repo.create_sighting(sighting)

        # Notify pet owner if resolved
        owner_id = None
        pet_name = "your pet"
        if payload.pet_id:
            from sqlalchemy import select

            from pawguard.modules.companion_pet.models import CompanionPet

            stmt = select(CompanionPet).where(CompanionPet.id == payload.pet_id)
            pet = (await self._repo._session.execute(stmt)).scalar_one_or_none()
            if pet:
                owner_id = pet.owner_id
                pet_name = pet.name

        if owner_id is None and payload.lost_report_id:
            report = await self._repo.get_lost_report_by_id(payload.lost_report_id)
            if report:
                owner_id = report.user_id
                pet_name = report.pet_name

        if owner_id and self._notification_svc:
            try:
                from pawguard.modules.notifications.schemas import NotificationSend

                await self._notification_svc.send_notification(
                    payload=NotificationSend(
                        user_id=owner_id,
                        title=f"QR Safety Tag Sighting Reported for {pet_name}!",
                        body=(
                            f"{payload.finder_name} submitted a sighting of {pet_name} at "
                            f"{payload.location_address}. Contact phone: {payload.finder_phone}."
                        ),
                        notification_type="qr_sighting",
                        send_email=True,
                        send_push=True,
                    )
                )
            except Exception as exc:
                logger.warning("Failed to send sighting notification: %s", exc)

        return sighting

    async def report_found_pet(
        self,
        user_id: uuid.UUID,
        payload: FoundReportCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FoundReport:
        lock_token = str(uuid.uuid4())
        lock_acquired = False
        cache_svc = None
        ident_hash = ""
        if self._redis is not None and not is_null_redis(self._redis):
            ident_str = f"{user_id}:{payload.species}:{payload.breed_observed.strip().lower()}:{payload.location_address.strip().lower()}"
            ident_hash = hashlib.sha256(ident_str.encode()).hexdigest()[:16]
            cache_svc = CacheService(self._redis, namespace="lost_found")
            lock_acquired = await cache_svc.acquire_lock(
                f"lock:found:{user_id}:{ident_hash}", lock_token, expire_ms=10000
            )

        try:
            # Duplicate prevention check: return existing active report if identical
            existing = await self._repo.find_active_found_duplicate(
                user_id=user_id,
                species=payload.species,
                breed_observed=payload.breed_observed,
                location_address=payload.location_address,
            )
            if existing is not None and isinstance(existing, FoundReport):
                logger.info(
                    "duplicate_found_report_prevented",
                    user_id=str(user_id),
                    existing_report_id=str(existing.id),
                )
                return existing

            from pawguard.services.storage_service import StorageService

            # Determine photo keys and video key
            photo_keys = payload.photo_object_keys
            if photo_keys is None:
                photo_keys = [payload.photo_object_key] if payload.photo_object_key else []
            video_key = payload.video_object_key

            # Validate S3 objects if present
            if photo_keys or video_key:
                StorageService().validate_report_media(photo_keys, video_key)

            # Legacy primary key to store on report model
            primary_key = photo_keys[0] if photo_keys else payload.photo_object_key
            # Resolve legacy photo url if primary key is present
            photo_url = payload.photo_url
            if primary_key:
                with contextlib.suppress(Exception):
                    photo_url = StorageService().generate_public_url(object_key=primary_key)

            report = FoundReport(
                user_id=user_id,
                species=payload.species,
                breed_observed=payload.breed_observed.lower(),
                color_observed=payload.color_observed.lower(),
                collar_color=payload.collar_color,
                collar_description=payload.collar_description,
                marker_description=payload.marker_description,
                location_address=payload.location_address,
                latitude=payload.latitude,
                longitude=payload.longitude,
                found_at=payload.found_at,
                status=ReportStatus.ACTIVE,
                photo_url=photo_url,
                photo_object_key=primary_key,
            )
            await self._repo.create_found_report(report)
            await self._repo._session.flush()

            # Save ReportMedia entries
            media_items = []
            for idx, key in enumerate(photo_keys):
                media_items.append(
                    ReportMedia(
                        found_report_id=report.id,
                        media_type="photo",
                        object_key=key,
                        is_primary=(idx == 0),
                        display_order=idx,
                    )
                )
            if video_key:
                media_items.append(
                    ReportMedia(
                        found_report_id=report.id,
                        media_type="video",
                        object_key=video_key,
                        is_primary=False,
                        display_order=len(photo_keys),
                    )
                )

            for m in media_items:
                self._repo._session.add(m)
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
            reloaded = await self._repo.get_found_report_by_id(report.id)
            return reloaded or report
        finally:
            if lock_acquired and cache_svc is not None:
                await cache_svc.release_lock(f"lock:found:{user_id}:{ident_hash}", lock_token)

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
            page_params,
            sort,
            search_term=search_term,
            status=status,
            species=species,
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
            page_params,
            sort,
            search_term=search_term,
            status=status,
            species=species,
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
            page_params,
            sort,
            lost_report_id=lost_report_id,
            found_report_id=found_report_id,
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
        if status == MatchStatus.CONFIRMED:
            # Workflow 6: release each party's contact to the other when the
            # match is confirmed directly (non-claim path).
            await self._release_contacts(match)
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
            match.lost_report is not None and match.lost_report.user_id == claimant_user_id
        )
        is_found_reporter = (
            match.found_report is not None and match.found_report.user_id == claimant_user_id
        )
        if not is_lost_owner and not is_found_reporter:
            raise ForbiddenError("Only a reporter on this match may submit an ownership claim.")

        if match.status != MatchStatus.PENDING:
            raise ValidationFailedError("This match has already been reviewed; claims are closed.")
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
                        doc
                        for doc in (
                            "microchip_doc" if payload.microchip_doc_url else None,
                            "vet_bill" if payload.vet_bill_url else None,
                            "photo_proof" if payload.photo_proof_url else None,
                        )
                        if doc
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
            raise ValidationFailedError("No ownership claim has been submitted for this match yet.")
        if match.status != MatchStatus.PENDING:
            raise ValidationFailedError("This match has already been reviewed.")

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
                match.lost_report_id,
                actor_id=actor_id,
                ip_address=ip_address,
            )
            await self.resolve_found_report(
                match.found_report_id,
                actor_id=actor_id,
                ip_address=ip_address,
            )
            # Workflow 6: release each party's contact to the other so the dog
            # can be returned.
            await self._release_contacts(match)

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

    def _evaluate_match_score(
        self, lost: LostReport, found: FoundReport
    ) -> tuple[float, float, float, list[str]]:
        """Compute a confidence score (0-100) for a lost/found pair.

        Weight breakdown (total = 100):
            Breed match:            25.0
            Color match:            25.0
            Distance (Haversine):   20.0
            Temporal alignment:     15.0
            Collar color match:     10.0
            Marker overlap:          5.0

        Returns:
            (confidence_score, temporal_gap_days, match_reasons)
        """
        score = 0.0
        reasons: list[str] = []

        # 1. Breed match (max 25.0)
        if lost.breed == found.breed_observed:
            score += 25.0
            reasons.append("breed_exact")
        elif lost.breed in found.breed_observed or found.breed_observed in lost.breed:
            score += 15.0
            reasons.append("breed_partial")

        # 2. Color match (max 25.0)
        if lost.color == found.color_observed:
            score += 25.0
            reasons.append("color_exact")
        elif lost.color in found.color_observed or found.color_observed in lost.color:
            score += 15.0
            reasons.append("color_partial")

        # 3. Distance Match (max 20.0)
        dist = self._calculate_distance_km(
            float(lost.latitude) if lost.latitude is not None else None,
            float(lost.longitude) if lost.longitude is not None else None,
            float(found.latitude) if found.latitude is not None else None,
            float(found.longitude) if found.longitude is not None else None,
        )
        if dist <= 2.0:
            score += 20.0
            reasons.append("distance_near")
        elif dist <= 5.0:
            score += 12.0
            reasons.append("distance_close")
        elif dist <= 10.0:
            score += 6.0
            reasons.append("distance_moderate")

        # 4. Temporal alignment (max 15.0)
        lost_dt = lost.lost_at
        found_dt = found.found_at
        temporal_gap_days = abs((lost_dt - found_dt).total_seconds()) / 86400.0
        if temporal_gap_days <= 1:
            score += 15.0
            reasons.append("temporal_same_day")
        elif temporal_gap_days <= 3:
            score += 12.0
            reasons.append("temporal_within_3_days")
        elif temporal_gap_days <= 7:
            score += 9.0
            reasons.append("temporal_within_week")
        elif temporal_gap_days <= 14:
            score += 6.0
            reasons.append("temporal_within_2_weeks")
        elif temporal_gap_days <= 30:
            score += 3.0
            reasons.append("temporal_within_month")

        # 5. Collar color match (max 10.0)
        if (
            lost.collar_color
            and found.collar_color
            and lost.collar_color.lower() == found.collar_color.lower()
        ):
            score += 10.0
            reasons.append("collar_color_match")

        # 6. Marker description overlap (max 5.0)
        if lost.marker_description and found.marker_description:
            lost_markers = {
                m.strip().lower() for m in lost.marker_description.split(",") if m.strip()
            }
            found_markers = {
                m.strip().lower() for m in found.marker_description.split(",") if m.strip()
            }
            overlap = lost_markers & found_markers
            if overlap:
                marker_score = min(len(overlap) * 2.5, 5.0)
                score += marker_score
                reasons.append("markers_overlap")

        score = round(score, 2)
        temporal_gap_days = round(temporal_gap_days, 2)
        return score, round(dist, 2), temporal_gap_days, reasons

    async def _run_matching_for_lost(self, lost: LostReport) -> None:
        active_founds = await self._repo.list_found_reports(status=ReportStatus.ACTIVE)
        for found in active_founds:
            score, dist_km, gap_days, reasons = self._evaluate_match_score(lost, found)
            if score >= 50.0:
                match = ReportMatch(
                    lost_report_id=lost.id,
                    found_report_id=found.id,
                    confidence_score=score,
                    distance_km=dist_km,
                    temporal_gap_days=gap_days,
                    match_reasons=reasons,
                    status=MatchStatus.PENDING,
                )
                await self._repo.create_match(match)
                await self._notify_match(match, lost=lost, found=found)

    async def _run_matching_for_found(self, found: FoundReport) -> None:
        active_losts = await self._repo.list_lost_reports(status=ReportStatus.ACTIVE)
        for lost in active_losts:
            score, dist_km, gap_days, reasons = self._evaluate_match_score(lost, found)
            if score >= 50.0:
                match = ReportMatch(
                    lost_report_id=lost.id,
                    found_report_id=found.id,
                    confidence_score=score,
                    distance_km=dist_km,
                    temporal_gap_days=gap_days,
                    match_reasons=reasons,
                    status=MatchStatus.PENDING,
                )
                await self._repo.create_match(match)
                await self._notify_match(match, lost=lost, found=found)

    async def _notify_match(
        self,
        match: ReportMatch,
        lost: LostReport | None = None,
        found: FoundReport | None = None,
    ) -> None:
        """Email and push the lost-pet owner and the found-pet reporter about a possible match."""
        if self._arq is None and self._notification_svc is None:
            return
        if lost is None or found is None:
            loaded_match = await self._repo.get_match_by_id(match.id)
            if loaded_match is not None:
                lost = loaded_match.lost_report
                found = loaded_match.found_report
        if lost is None or found is None:
            return

        lost_user = getattr(lost, "user", None)
        found_user = getattr(found, "user", None)
        pet_name = lost.pet_name if lost.pet_name else "your pet"
        subject = f"Possible match for {pet_name}!"
        body = (
            f"We found a possible match for {pet_name} (match confidence "
            f"{match.confidence_score:.0f}%). Our team is reviewing it - "
            "please check the PawGuard lost & found portal for details."
        )
        if self._arq is not None:
            try:
                if lost_user is not None and getattr(lost_user, "email", None):
                    await self._arq.enqueue_job(
                        "send_notification_email_job",
                        to=lost_user.email,
                        subject=subject,
                        body=body,
                    )
                if found_user is not None and getattr(found_user, "email", None):
                    await self._arq.enqueue_job(
                        "send_notification_email_job",
                        to=found_user.email,
                        subject=subject,
                        body=body,
                    )
            except Exception as exc:
                logger.warning("Failed to notify lost/found match %s: %s", match.id, exc)

        # Push notifications to both parties
        if self._notification_svc:
            try:
                push_user_ids = []
                if lost.user_id:
                    push_user_ids.append(lost.user_id)
                if found.user_id:
                    push_user_ids.append(found.user_id)
                if push_user_ids:
                    await self._notification_svc._send_push_to_users(
                        push_user_ids,
                        subject,
                        body,
                        f"/lost-found/lost/{match.lost_report_id}/matches",
                    )
            except Exception as exc:
                logger.warning("Failed to send match push notification %s: %s", match.id, exc)

        # Workflow 6: administrators are notified so they can oversee the
        # reunification from a potential match.
        try:
            await self._notify_admins_of_match(match, lost=lost)
        except Exception as exc:
            logger.warning("Failed to notify admins of match %s: %s", match.id, exc)

    async def _notify_admins_of_match(
        self, match: ReportMatch, lost: LostReport | None = None
    ) -> None:
        if self._notification_svc is None:
            return
        pet_name = lost.pet_name if (lost and lost.pet_name) else "a pet"
        await self._notification_svc.broadcast(
            BroadcastCreate(
                title=f"New lost & found match: {pet_name}",
                body=(
                    f"A potential match (confidence {match.confidence_score:.0f}%) was "
                    f"identified between a lost and a found report. Please review the "
                    f"reunification claim."
                ),
                notification_type="lost_found_match",
                action_url=f"/lost-found/lost/{match.lost_report_id}/matches",
                target_roles=["rescue_centre_admin", "system:admin"],
            ),
            user_ids=[],
            actor_id=None,
        )

    async def _release_contacts(self, match: ReportMatch) -> None:
        """Workflow 6: once a match is confirmed, release each reporter's contact
        details to the other party (via in-app notification + push) so they can
        arrange the dog's return. API responses keep contact details masked otherwise."""
        if self._notification_svc is None:
            return
        lost = match.lost_report
        found = match.found_report
        if lost is None or found is None:
            return
        lost_user = lost.user
        found_user = found.user
        if lost_user is None or found_user is None:
            return

        await self._send_contact_release(
            to_user=lost_user,
            from_user=found_user,
            pet_name=lost.pet_name,
            title="Reunification confirmed - finder contact",
            body=(
                f"Your lost report is confirmed. The finder can be reached at: "
                f"{found_user.full_name} ({found_user.email}, {found_user.phone})."
            ),
        )
        await self._send_contact_release(
            to_user=found_user,
            from_user=lost_user,
            pet_name=lost.pet_name,
            title="Reunification confirmed - owner contact",
            body=(
                f"The owner of the pet you found can be reached at: "
                f"{lost_user.full_name} ({lost_user.email}, {lost_user.phone})."
            ),
        )

        # Push notifications for contact release
        try:
            await self._notification_svc._send_push_to_users(
                [lost_user.id, found_user.id],
                "Pet Reunification - Contact Released",
                "Contact details have been released for a confirmed reunification. Check your notifications.",
                f"/lost-found/lost/{match.lost_report_id}/matches",
            )
        except Exception as exc:
            logger.warning("Failed to send contact release push: %s", exc)

    async def _send_contact_release(
        self, to_user: Any, from_user: Any, pet_name: str | None, title: str, body: str
    ) -> None:
        if self._notification_svc is None:
            return
        try:
            await self._notification_svc.send_notification(
                payload=NotificationSend(
                    user_id=to_user.id,
                    title=title,
                    body=body,
                    notification_type="lost_found_contact_release",
                    send_email=False,
                    send_push=True,
                ),
                user_email=getattr(to_user, "email", None),
            )
        except Exception as exc:
            logger.warning(
                "Failed to release contact to user %s for pet %s: %s",
                to_user.id,
                pet_name,
                exc,
            )
