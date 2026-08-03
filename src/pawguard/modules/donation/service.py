"""DonationService: owns donor registers, contributions, and sponsorships (RULE-003)."""

import uuid
from datetime import UTC, date, datetime
from logging import getLogger

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
    DogSponsorship,
    Donation,
    DonationStatus,
    DonorProfile,
    SponsorshipStatus,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.schemas import (
    DonationCreate,
    DonationOrderResponse,
    DonationResponse,
    DonorProfileCreate,
    DonorProfileResponse,
    DonorProfileUpdate,
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
            raise ConflictError("You are already registered as a donor.")

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

        tx_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        donation = Donation(
            donor_id=donor.id,
            dog_id=payload.dog_id,
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
                },
            )
        await self._generate_receipt(res)
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

        donation = Donation(
            donor_id=donor.id,
            dog_id=payload.dog_id,
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
        donor = await self.get_or_create_donor(user_id)

        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

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
