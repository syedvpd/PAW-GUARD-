"""DonationService: owns donor registers, contributions, and sponsorships (RULE-003)."""

import calendar
import uuid
from datetime import UTC, date, datetime
from logging import getLogger

from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.config import get_settings
from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.payments import PaymentGateway, PaymentGatewayError, WebhookEvent
from pawguard.core.pdf_generation import generate_tax_receipt
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.donation.models import (
    CampaignStatus,
    DogSponsorship,
    Donation,
    DonationCampaign,
    DonationStatus,
    DonationType,
    DonorProfile,
    RecurringStatus,
    RecurringSubscription,
    SponsorshipStatus,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.schemas import (
    DonationCampaignCreate,
    DonationCampaignResponse,
    DonationCampaignUpdate,
    DonationCreate,
    DonationOrderResponse,
    DonationResponse,
    DonorProfileCreate,
    DonorProfileResponse,
    DonorProfileUpdate,
    RecurringSubscriptionCreate,
    SponsorshipCreate,
)
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.storage.models import FileFolder, StoredFile
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService

logger = getLogger(__name__)


class DonationService:
    def __init__(
        self,
        repository: DonationRepository,
        dog_repo: DogRepository,
        payment_gateway: PaymentGateway | None = None,
        audit_service: AuditService | None = None,
        notification_service: NotificationService | None = None,
        storage_service: StorageService | None = None,
    ) -> None:
        self._repo = repository
        self._dog_repo = dog_repo
        self._gateway = payment_gateway
        self._audit = audit_service
        self._notification_svc = notification_service
        self._storage = storage_service

    async def _generate_receipt(self, donation: Donation) -> None:
        if self._storage is None:
            return
        try:
            donor_name = (
                donation.donor.user.full_name
                if donation.donor and donation.donor.user
                else "Donor"
            )
            settings = get_settings()
            pdf_bytes = generate_tax_receipt(
                donor_name=donor_name,
                amount=float(donation.amount),
                currency=donation.currency,
                transaction_id=donation.transaction_id or "",
                donation_date=donation.created_at,
                org_name=settings.org_name,
                org_address=settings.org_address,
            )
            object_key = self._storage.build_object_key(
                folder="documents", filename=f"receipt_{donation.id}.pdf"
            )
            self._storage.put_object(
                object_key=object_key,
                content=pdf_bytes,
                content_type="application/pdf",
            )
            stored = StoredFile(
                object_key=object_key,
                original_filename=f"tax_receipt_{donation.id}.pdf",
                mime_type="application/pdf",
                file_size=len(pdf_bytes),
                folder=FileFolder.DOCUMENTS.value,
                is_uploaded=True,
                uploaded_at=datetime.now(UTC),
                entity_type="donation",
                entity_id=donation.id,
            )
            self._repo._session.add(stored)
            donation.receipt_file_key = object_key
            await self._repo._session.flush()

            # Automated tax receipt delivery via notification (PRD 3.11)
            if self._notification_svc and donation.donor:
                try:
                    from pawguard.modules.notifications.schemas import NotificationCreate
                    await self._notification_svc.create_notification(
                        payload=NotificationCreate(
                            user_id=donation.donor.user_id,
                            title="Tax Receipt Available",
                            body=(
                                "Your tax-deductible receipt for donation "
                                f"{donation.transaction_id or donation.id} is "
                                "ready for download."
                            ),
                            notification_type="tax_receipt",
                            action_url=f"/api/v1/donations/{donation.id}/receipt",
                        )
                    )
                except Exception as notif_exc:
                    logger.warning(
                        "Failed to send notification for tax receipt delivery on donation %s: %s",
                        donation.id,
                        notif_exc,
                        exc_info=True,
                    )

            if self._audit:
                await self._audit.record(
                    event_type=AuthAuditEventType.DONATION_RECEIPT_ISSUED,
                    actor_id=None,
                    ip_address="",
                    user_agent="",
                    metadata={
                        "donation_id": str(donation.id),
                        "amount": str(donation.amount),
                        "currency": donation.currency,
                    },
                )
        except Exception:
            logger.warning("Failed to generate receipt for donation %s", donation.id, exc_info=True)

    async def register_donor(
        self,
        user_id: uuid.UUID,
        payload: DonorProfileCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DonorProfile:
        existing = await self._repo.get_donor_by_user_id(user_id)
        if existing is not None:
            if payload.tax_identifier:
                existing.tax_identifier = payload.tax_identifier
            if payload.notes:
                existing.notes = payload.notes
            session = getattr(self._repo, "_session", None)
            if session is not None and hasattr(session, "flush"):
                res = session.flush()
                if hasattr(res, "__await__"):
                    await res
                if hasattr(session, "refresh"):
                    ref = session.refresh(existing)
                    if hasattr(ref, "__await__"):
                        await ref
            return existing

        profile = DonorProfile(
            user_id=user_id,
            tax_identifier=payload.tax_identifier,
            notes=payload.notes,
        )
        result = await self._repo.create_donor_profile(profile)

        # Self-service donor registration is a public mutation: keep an audit
        # trail of who registered, from where, and when (PRR §6.1).
        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.DONOR_REGISTERED,
                actor_id=actor_id or user_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "donor_id": str(result.id),
                    "user_id": str(user_id),
                },
            )
        return result

    async def get_or_create_donor(self, user_id: uuid.UUID) -> DonorProfile:
        donor = await self._repo.get_donor_by_user_id(user_id)
        if donor is None:
            donor = DonorProfile(user_id=user_id)
            await self._repo.create_donor_profile(donor)
        return donor

    async def _validate_campaign_open(
        self, campaign_id: uuid.UUID | None
    ) -> DonationCampaign | None:
        """Ensure a target campaign exists and is currently accepting
        donations (PRR 3.1.7 campaign drives)."""
        if campaign_id is None:
            return None
        campaign = await self._repo.get_campaign_by_id(campaign_id)
        if campaign is None:
            raise NotFoundError("Donation campaign not found.")
        today = datetime.now(UTC).date()
        if campaign.status != CampaignStatus.ACTIVE:
            raise ValidationFailedError("This donation campaign is not accepting donations.")
        if campaign.start_date > today:
            raise ValidationFailedError("This donation campaign has not started yet.")
        if campaign.end_date is not None and campaign.end_date < today:
            raise ValidationFailedError("This donation campaign has ended.")
        return campaign

    async def _refresh_campaign_progress(
        self, campaign_id: uuid.UUID | None
    ) -> None:
        """After a successful donation, recompute raised totals and auto-complete
        the campaign when its goal has been reached."""
        if campaign_id is None:
            return
        campaign = await self._repo.get_campaign_by_id(campaign_id)
        if campaign is None or campaign.status == CampaignStatus.COMPLETED:
            return
        raised, _ = await self._repo.get_campaign_totals(campaign_id)
        if raised >= float(campaign.target_amount):
            await self._repo.update_campaign(
                campaign_id,
                status=CampaignStatus.COMPLETED,
                goal_reached_at=datetime.now(UTC),
            )
            if self._audit:
                await self._audit.record(
                    event_type=AuthAuditEventType.DONATION_CAMPAIGN_COMPLETED,
                    actor_id=None,
                    ip_address="",
                    user_agent="",
                    metadata={
                        "campaign_id": str(campaign_id),
                        "raised_amount": str(raised),
                        "target_amount": str(campaign.target_amount),
                        "currency": campaign.currency,
                    },
                )

    async def make_donation(
        self,
        user_id: uuid.UUID,
        payload: DonationCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Donation:
        donor = await self.get_or_create_donor(user_id)

        if payload.dog_id is not None:
            dog = await self._dog_repo.get_by_id(payload.dog_id)
            if dog is None:
                raise NotFoundError("Dog profile not found.")

        _ = await self._validate_campaign_open(payload.campaign_id)

        tx_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        donation = Donation(
            donor_id=donor.id,
            dog_id=payload.dog_id,
            campaign_id=payload.campaign_id,
            amount=payload.amount,
            currency=payload.currency,
            donation_type=payload.donation_type,
            status=DonationStatus.SUCCESS,
            transaction_id=tx_id,
            notes=payload.notes,
        )
        await self._repo.create_donation(donation)
        res = await self._repo.get_donation_by_id(donation.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created donation record.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_RECEIVED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "donation_id": str(res.id),
                    "donor_id": str(donor.id),
                    "amount": str(payload.amount),
                    "currency": payload.currency,
                    "manual": True,
                    "campaign_id": str(payload.campaign_id) if payload.campaign_id else None,
                },
            )
        await self._generate_receipt(res)
        await self._refresh_campaign_progress(payload.campaign_id)
        return res

    async def get_donation(self, donation_id: uuid.UUID) -> Donation:
        donation = await self._repo.get_donation_by_id(donation_id)
        if donation is None:
            raise NotFoundError("Donation record not found.")
        return donation

    async def initiate_online_donation(
        self,
        user_id: uuid.UUID,
        payload: DonationCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DonationOrderResponse:
        """Create a PENDING donation and an order with the configured payment
        gateway. The client uses the returned order details to open the
        provider's checkout; the donation is only marked SUCCESS once
        `verify_donation_payment` (or the provider webhook) confirms it."""
        if self._gateway is None:
            raise ValidationFailedError("Online payments are not configured for this deployment.")

        donor = await self.get_or_create_donor(user_id)

        if payload.dog_id is not None:
            dog = await self._dog_repo.get_by_id(payload.dog_id)
            if dog is None:
                raise NotFoundError("Dog profile not found.")

        _ = await self._validate_campaign_open(payload.campaign_id)

        donation = Donation(
            donor_id=donor.id,
            dog_id=payload.dog_id,
            campaign_id=payload.campaign_id,
            amount=payload.amount,
            currency=payload.currency,
            donation_type=payload.donation_type,
            status=DonationStatus.PENDING,
            notes=payload.notes,
            payment_provider=self._gateway.provider_name,
        )
        await self._repo.create_donation(donation)

        # Razorpay caps `receipt` at 40 chars; a bare UUID (36 chars) fits, a
        # prefixed one doesn't.
        receipt = str(donation.id)
        try:
            order = await self._gateway.create_order(
                amount=payload.amount,
                currency=payload.currency,
                receipt=receipt,
                notes={"donation_id": str(donation.id), "donor_id": str(donor.id)},
            )
        except PaymentGatewayError as exc:
            await self._repo.update_donation_status(donation.id, DonationStatus.FAILED)
            raise ValidationFailedError(str(exc)) from exc

        await self._repo.update_gateway_fields(donation.id, gateway_order_id=order.order_id)

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_ORDER_CREATED,
                actor_id=actor_id or user_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "donation_id": str(donation.id),
                    "donor_id": str(donor.id),
                    "gateway_order_id": order.order_id,
                    "amount": str(payload.amount),
                    "currency": payload.currency,
                },
            )

        return DonationOrderResponse(
            donation_id=donation.id,
            provider=order.provider,
            order_id=order.order_id,
            amount=order.amount,
            currency=order.currency,
            checkout_key=order.checkout_key,
        )

    async def verify_donation_payment(
        self,
        donation_id: uuid.UUID,
        gateway_order_id: str,
        gateway_payment_id: str,
        gateway_signature: str,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Donation:
        if self._gateway is None:
            raise ValidationFailedError("Online payments are not configured for this deployment.")

        donation = await self.get_donation(donation_id)
        if donation.gateway_order_id != gateway_order_id:
            raise ValidationFailedError("Order reference does not match this donation.")
        if donation.status == DonationStatus.SUCCESS:
            return donation

        result = self._gateway.verify_payment_signature(
            order_id=gateway_order_id,
            payment_id=gateway_payment_id,
            signature=gateway_signature,
        )
        if not result.verified:
            await self._repo.update_gateway_fields(
                donation.id,
                status=DonationStatus.FAILED,
                gateway_payment_id=gateway_payment_id,
            )
            raise ValidationFailedError(
                result.failure_reason or "Payment verification failed."
            )

        tx_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        updated = await self._repo.update_gateway_fields(
            donation.id,
            status=DonationStatus.SUCCESS,
            gateway_payment_id=gateway_payment_id,
            gateway_signature=gateway_signature,
            transaction_id=tx_id,
        )
        if updated is None:
            raise NotFoundError("Donation record not found.")
        res = await self._repo.get_donation_by_id(updated.id)
        if res is None:
            raise NotFoundError("Donation record not found.")

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_RECEIVED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "donation_id": str(res.id),
                    "amount": str(res.amount),
                    "currency": res.currency,
                    "gateway_payment_id": gateway_payment_id,
                    "verified_online": True,
                },
            )
        await self._generate_receipt(res)
        await self._refresh_campaign_progress(res.campaign_id)
        return res

    async def handle_gateway_webhook(self, payload: bytes, signature: str) -> None:
        """Server-to-server confirmation, in case the client never returns to
        call `verify_donation_payment` (closed tab, network drop, etc.)."""
        if self._gateway is None:
            raise ValidationFailedError("Online payments are not configured for this deployment.")

        event: WebhookEvent = self._gateway.parse_webhook(payload=payload, signature=signature)
        if event.order_id is None:
            return

        donation = await self._repo.get_donation_by_gateway_order_id(event.order_id)
        if donation is None or donation.status == DonationStatus.SUCCESS:
            return

        if event.is_success:
            tx_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
            await self._repo.update_gateway_fields(
                donation.id,
                status=DonationStatus.SUCCESS,
                gateway_payment_id=event.payment_id,
                transaction_id=tx_id,
            )
            if self._audit:
                await self._audit.record(
                    event_type=AuthAuditEventType.DONATION_RECEIVED,
                    actor_id=None,
                    ip_address="",
                    user_agent="",
                    metadata={
                        "donation_id": str(donation.id),
                        "gateway_payment_id": event.payment_id,
                        "source": "webhook",
                    },
                )
            refreshed = await self._repo.get_donation_by_id(donation.id)
            if refreshed is not None:
                await self._generate_receipt(refreshed)
                await self._refresh_campaign_progress(refreshed.campaign_id)
        elif event.event_type == "payment.failed":
            await self._repo.update_gateway_fields(donation.id, status=DonationStatus.FAILED)
            if self._audit:
                await self._audit.record(
                    event_type=AuthAuditEventType.DONATION_STATUS_CHANGED,
                    actor_id=None,
                    ip_address="",
                    user_agent="",
                    metadata={
                        "donation_id": str(donation.id),
                        "new_status": DonationStatus.FAILED.value,
                        "source": "webhook",
                    },
                )

    async def list_donations_for_user(self, user_id: uuid.UUID) -> list[Donation]:
        donor = await self._repo.get_donor_by_user_id(user_id)
        if donor is None:
            return []
        return list(await self._repo.get_donations_by_donor(donor.id))

    async def update_donor(
        self,
        donor_id: uuid.UUID,
        payload: DonorProfileUpdate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DonorProfile:
        donor = await self._repo.get_donor_by_id(donor_id)
        if donor is None:
            raise NotFoundError("Donor profile not found.")
        updated = await self._repo.update_donor_profile(
            donor_id,
            **payload.model_dump(exclude_unset=True),
        )
        if updated is None:
            raise NotFoundError("Donor profile not found after update.")
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONOR_PROFILE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"donor_id": str(donor_id)},
            )
        return updated

    async def update_donation_status(
        self,
        donation_id: uuid.UUID,
        status: DonationStatus,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Donation:
        donation = await self._repo.get_donation_by_id(donation_id)
        if donation is None:
            raise NotFoundError("Donation record not found.")
        old_status = donation.status
        updated = await self._repo.update_donation_status(donation_id, status)
        if updated is None:
            raise NotFoundError("Failed to update donation status.")
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_STATUS_CHANGED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "donation_id": str(donation_id),
                    "old_status": old_status.value if hasattr(old_status, "value") else old_status,
                    "new_status": status.value,
                },
            )
        return updated

    async def soft_delete_donor(
        self,
        donor_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        donor = await self._repo.get_donor_by_id(donor_id)
        if donor is None:
            raise NotFoundError("Donor profile not found.")
        await self._repo.soft_delete_donor(donor_id)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONOR_PROFILE_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"donor_id": str(donor_id)},
            )

    async def list_donations_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        donation_type: str | None = None,
        status: DonationStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PaginatedResponse[DonationResponse]:
        results, total = await self._repo.paginate_donations(
            page=page,
            sort=sort,
            search_term=search_term,
            donation_type=donation_type,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
        return PaginatedResponse(
            data=[DonationResponse.model_validate(d) for d in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def list_donors_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
    ) -> PaginatedResponse[DonorProfileResponse]:
        results, total = await self._repo.paginate_donors(
            page=page,
            sort=sort,
            search_term=search_term,
        )
        return PaginatedResponse(
            data=[DonorProfileResponse.model_validate(d) for d in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def bulk_update_status(
        self,
        ids: list[uuid.UUID],
        status: DonationStatus,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_update_donation_status(ids, status)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_STATUS_CHANGED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "donation_ids": [str(i) for i in ids],
                    "new_status": status.value,
                    "count": count,
                },
            )
        return count

    async def bulk_soft_delete(
        self,
        ids: list[uuid.UUID],
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_soft_delete_donors(ids)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONOR_PROFILE_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"donor_ids": [str(i) for i in ids], "count": count},
            )
        return count

    async def create_sponsorship(
        self,
        user_id: uuid.UUID,
        payload: SponsorshipCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DogSponsorship:
        if payload.monthly_amount <= 0:
            raise ValidationFailedError("Monthly sponsorship amount must be greater than zero.")

        donor = await self.get_or_create_donor(user_id)

        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError(f"Dog profile with ID '{payload.dog_id}' was not found.")

        if hasattr(dog, "status") and dog.status:
            status_val = dog.status.value if hasattr(dog.status, "value") else str(dog.status).lower()
            if status_val in ("adopted", "deceased"):
                raise ConflictError(
                    f"Dog with ID '{payload.dog_id}' has already been {status_val} and cannot be sponsored."
                )

        existing_sponsorships = await self._repo.get_sponsorships_for_donor(donor.id)
        for sp in existing_sponsorships:
            if sp.dog_id == payload.dog_id and sp.status == SponsorshipStatus.ACTIVE:
                raise ConflictError(
                    f"Dog with ID '{payload.dog_id}' has already been sponsored by you."
                )

        now = datetime.now(UTC)
        sponsorship = DogSponsorship(
            donor_id=donor.id,
            dog_id=payload.dog_id,
            monthly_amount=payload.monthly_amount,
            currency=payload.currency,
            status=SponsorshipStatus.ACTIVE,
            next_charge_date=now.date(),
            started_at=now,
        )
        await self._repo.create_sponsorship(sponsorship)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.SPONSORSHIP_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "sponsorship_id": str(sponsorship.id),
                    "donor_id": str(donor.id),
                    "dog_id": str(payload.dog_id),
                    "monthly_amount": str(payload.monthly_amount),
                    "currency": payload.currency,
                },
            )
        return sponsorship

    async def pause_sponsorship(
        self,
        sponsorship_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DogSponsorship:
        sponsorship = await self._repo.get_sponsorship_by_id(sponsorship_id)
        if sponsorship is None:
            raise NotFoundError("Sponsorship not found.")
        if sponsorship.status != SponsorshipStatus.ACTIVE:
            raise ValidationFailedError("Only active sponsorships can be paused.")

        updated = await self._repo.update_sponsorship_status(
            sponsorship_id, SponsorshipStatus.PAUSED
        )
        if updated is None:
            raise NotFoundError("Failed to update sponsorship status.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.SPONSORSHIP_PAUSED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"sponsorship_id": str(sponsorship_id)},
            )
        return updated

    async def cancel_sponsorship(
        self,
        sponsorship_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DogSponsorship:
        sponsorship = await self._repo.get_sponsorship_by_id(sponsorship_id)
        if sponsorship is None:
            raise NotFoundError("Sponsorship not found.")

        updated = await self._repo.cancel_sponsorship(
            sponsorship_id, datetime.now(UTC),
        )
        if updated is None:
            raise NotFoundError("Failed to cancel sponsorship.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.SPONSORSHIP_CANCELLED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"sponsorship_id": str(sponsorship_id)},
            )
        return updated

    async def list_sponsorships_for_donor(
        self, user_id: uuid.UUID
    ) -> list[DogSponsorship]:
        donor = await self._repo.get_donor_by_user_id(user_id)
        if donor is None:
            return []
        return list(await self._repo.get_sponsorships_for_donor(donor.id))

    async def list_all_sponsorships(self) -> list[DogSponsorship]:
        return list(await self._repo.list_all_sponsorships())

    async def get_sponsorship(
        self, sponsorship_id: uuid.UUID
    ) -> DogSponsorship:
        sponsorship = await self._repo.get_sponsorship_by_id(sponsorship_id)
        if sponsorship is None:
            raise NotFoundError("Sponsorship not found.")
        return sponsorship

    # ── Recurring subscriptions (audit 3.11) ──────────────────────────

    async def create_recurring_subscription(
        self,
        user_id: uuid.UUID,
        payload: RecurringSubscriptionCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RecurringSubscription:
        donor = await self.get_or_create_donor(user_id)

        now = datetime.now(UTC)
        subscription = RecurringSubscription(
            donor_id=donor.id,
            amount=payload.amount,
            currency=payload.currency,
            frequency=payload.frequency,
            status=RecurringStatus.ACTIVE,
            next_charge_date=now.date(),
            started_at=now,
        )
        await self._repo.create_recurring_subscription(subscription)

        # Create the initial PENDING donation (mirrors sponsorship charge pattern)
        donation = Donation(
            donor_id=donor.id,
            amount=payload.amount,
            currency=payload.currency,
            donation_type=DonationType.RECURRING,
            status=DonationStatus.PENDING,
            recurring_subscription_id=subscription.id,
            notes="Initial recurring donation charge.",
        )
        await self._repo.create_donation(donation)

        # Attempt to create a gateway order for online payment
        if self._gateway is not None:
            try:
                order = await self._gateway.create_order(
                    amount=payload.amount,
                    currency=payload.currency,
                    receipt=str(donation.id),
                    notes={
                        "recurring_subscription_id": str(subscription.id),
                        "donor_id": str(donor.id),
                    },
                )
                donation.payment_provider = order.provider
                donation.gateway_order_id = order.order_id
                donation.notes = "Recurring donation order initiated; awaiting payment."
                await self._repo.update_gateway_fields(
                    donation.id,
                    payment_provider=order.provider,
                    gateway_order_id=order.order_id,
                    notes=donation.notes,
                )
            except PaymentGatewayError:
                pass

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_RECEIVED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "recurring_subscription_id": str(subscription.id),
                    "donor_id": str(donor.id),
                    "amount": str(payload.amount),
                    "currency": payload.currency,
                    "recurring": True,
                },
            )
        return subscription

    async def cancel_recurring_subscription(
        self,
        subscription_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RecurringSubscription:
        subscription = await self._repo.get_recurring_subscription_by_id(
            subscription_id,
        )
        if subscription is None:
            raise NotFoundError("Recurring subscription not found.")
        if subscription.status == RecurringStatus.CANCELLED:
            raise ValidationFailedError("Subscription is already cancelled.")

        updated = await self._repo.cancel_recurring_subscription(
            subscription_id,
            cancelled_at=datetime.now(UTC),
        )
        if updated is None:
            raise NotFoundError("Failed to cancel recurring subscription.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.SPONSORSHIP_CANCELLED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"recurring_subscription_id": str(subscription_id)},
            )
        return updated

    async def charge_due_recurring_subscriptions(
        self, session: AsyncSession
    ) -> list[Donation]:
        """Charge all due recurring subscriptions.

        Returns the list of created PENDING Donation records. On success
        the subscription's next_charge_date is advanced by one month.
        """
        repo = DonationRepository(session)
        today = datetime.now(UTC).date()
        subscriptions = await repo.get_due_recurring_subscriptions(today)
        created: list[Donation] = []

        for sub in subscriptions:
            if await repo.has_pending_donation_for_subscription(sub.id):
                continue

            donation = Donation(
                donor_id=sub.donor_id,
                amount=sub.amount,
                currency=sub.currency,
                donation_type=DonationType.RECURRING,
                status=DonationStatus.PENDING,
                recurring_subscription_id=sub.id,
                notes="Monthly recurring donation charge.",
            )

            if self._gateway is not None:
                try:
                    order = await self._gateway.create_order(
                        amount=sub.amount,
                        currency=sub.currency,
                        receipt=str(donation.id),
                        notes={
                            "recurring_subscription_id": str(sub.id),
                            "donor_id": str(sub.donor_id),
                        },
                    )
                    donation.payment_provider = order.provider
                    donation.gateway_order_id = order.order_id
                    donation.notes = (
                        "Recurring donation order initiated; awaiting payment."
                    )
                except PaymentGatewayError:
                    pass

            await repo.create_donation(donation)
            created.append(donation)

            # Advance next_charge_date by one month
            next_date = sub.next_charge_date.month + 1
            year = sub.next_charge_date.year
            if next_date > 12:
                next_date = 1
                year += 1
            day = min(
                sub.next_charge_date.day,
                calendar.monthrange(year, next_date)[1],
            )
            new_charge_date = sub.next_charge_date.replace(
                year=year, month=next_date, day=day,
            )
            await repo.advance_recurring_charge_date(sub.id, new_charge_date)

            # Create in-app notification for the donor
            if sub.donor and sub.donor.user_id and self._notification_svc:
                try:
                    from pawguard.modules.notifications.schemas import (
                        NotificationCreate,
                    )

                    await self._notification_svc.create_notification(
                        payload=NotificationCreate(
                            user_id=sub.donor.user_id,
                            title="Monthly Recurring Donation Charge",
                            body=(
                                f"Your recurring donation of {sub.amount} "
                                f"{sub.currency} is now due. We'll let you "
                                f"know once your payment has been received."
                            ),
                            notification_type="recurring_donation_charge",
                        )
                    )
                except Exception as notif_exc:
                    logger.warning(
                        "Failed to send notification for recurring charge %s: %s",
                        sub.id,
                        notif_exc,
                        exc_info=True,
                    )

        await session.commit()
        return created

    # ── Donation campaigns (PRR 3.1.7 / 3.11) ─────────────────────────────

    async def create_campaign(
        self,
        payload: DonationCampaignCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DonationCampaign:
        if payload.end_date is not None and payload.end_date < payload.start_date:
            raise ValidationFailedError("Campaign end date cannot be before its start date.")

        campaign = DonationCampaign(
            name=payload.name,
            description=payload.description,
            target_amount=payload.target_amount,
            currency=payload.currency,
            campaign_type=payload.campaign_type,
            status=payload.status,
            start_date=payload.start_date,
            end_date=payload.end_date,
            created_by_id=actor_id,
        )
        result = await self._repo.create_campaign(campaign)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_CAMPAIGN_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "campaign_id": str(result.id),
                    "name": result.name,
                    "target_amount": str(result.target_amount),
                    "currency": result.currency,
                    "campaign_type": result.campaign_type.value
                    if hasattr(result.campaign_type, "value") else result.campaign_type,
                },
            )
        return result

    async def update_campaign(
        self,
        campaign_id: uuid.UUID,
        payload: DonationCampaignUpdate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DonationCampaign:
        existing = await self._repo.get_campaign_by_id(campaign_id)
        if existing is None:
            raise NotFoundError("Donation campaign not found.")

        values = payload.model_dump(exclude_unset=True)
        start = values.get("start_date", existing.start_date)
        end = values.get("end_date", existing.end_date)
        if end is not None and end < start:
            raise ValidationFailedError("Campaign end date cannot be before its start date.")

        updated = await self._repo.update_campaign(campaign_id, **values)
        if updated is None:
            raise NotFoundError("Donation campaign not found after update.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_CAMPAIGN_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"campaign_id": str(campaign_id), "changed_fields": sorted(values)},
            )
        return updated

    async def soft_delete_campaign(
        self,
        campaign_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        campaign = await self._repo.get_campaign_by_id(campaign_id)
        if campaign is None:
            raise NotFoundError("Donation campaign not found.")
        await self._repo.soft_delete_campaign(campaign_id)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_CAMPAIGN_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"campaign_id": str(campaign_id), "name": campaign.name},
            )

    async def get_campaign(self, campaign_id: uuid.UUID) -> DonationCampaign:
        campaign = await self._repo.get_campaign_by_id(campaign_id)
        if campaign is None:
            raise NotFoundError("Donation campaign not found.")
        return campaign

    async def list_campaigns_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: CampaignStatus | None = None,
        campaign_type: str | None = None,
    ) -> PaginatedResponse[DonationCampaignResponse]:
        results, total = await self._repo.paginate_campaigns(
            page=page,
            sort=sort,
            search_term=search_term,
            status=status,
            campaign_type=campaign_type,
        )
        return PaginatedResponse(
            data=[await self._to_campaign_response(c) for c in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def list_active_campaigns(self) -> list[DonationCampaign]:
        """Public listing of currently accepting campaigns (PRR 3.1.7)."""
        campaigns = await self._repo.list_active_campaigns(datetime.now(UTC).date())
        return [
            c for c in campaigns
            if c.end_date is None or c.end_date >= datetime.now(UTC).date()
        ]

    async def _to_campaign_response(self, campaign: DonationCampaign) -> DonationCampaignResponse:
        raised, donor_count = await self._repo.get_campaign_totals(campaign.id)
        progress = (
            (raised / float(campaign.target_amount) * 100.0)
            if float(campaign.target_amount) > 0 else 0.0
        )
        return DonationCampaignResponse(
            id=campaign.id,
            name=campaign.name,
            description=campaign.description,
            target_amount=float(campaign.target_amount),
            currency=campaign.currency,
            campaign_type=campaign.campaign_type,
            status=campaign.status,
            start_date=campaign.start_date,
            end_date=campaign.end_date,
            raised_amount=raised,
            donor_count=donor_count,
            progress_percentage=round(min(progress, 100.0), 2),
            goal_reached_at=campaign.goal_reached_at,
            created_at=campaign.created_at,
        )
