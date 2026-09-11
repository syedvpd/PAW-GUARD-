"""Business logic service for Invoicing & Service Fee Collection."""

import io
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams
from pawguard.core.payments.base import PaymentGateway, PaymentGatewayError, WebhookEvent
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.invoice.models import Invoice, InvoiceStatus, InvoiceType
from pawguard.modules.invoice.repository import InvoiceRepository
from pawguard.modules.invoice.schemas import InvoiceCreate, InvoiceStatusUpdate
from pawguard.modules.notifications.service import NotificationService
from pawguard.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class InvoiceService:
    def __init__(
        self,
        repository: InvoiceRepository,
        payment_gateway: PaymentGateway | None = None,
        audit_service: AuditService | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self._repo = repository
        self._payment_gateway = payment_gateway
        self._audit = audit_service
        self._notification_svc = notification_service

    async def create_draft_invoice(
        self,
        payload: InvoiceCreate,
        *,
        creator_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> Invoice:
        invoice_num = await self._repo.get_next_invoice_number()

        invoice = Invoice(
            id=uuid.uuid4(),
            invoice_number=invoice_num,
            invoice_type=payload.invoice_type,
            status=InvoiceStatus.DRAFT,
            billed_org_name=payload.billed_org_name,
            billed_user_id=payload.billed_user_id,
            recipient_email=str(payload.recipient_email) if payload.recipient_email else None,
            recipient_phone=payload.recipient_phone,
            amount=payload.amount,
            currency=payload.currency.upper(),
            description=payload.description,
            due_date=payload.due_date,
            source_module=payload.source_module,
            source_reference_id=payload.source_reference_id,
            created_by_id=creator_id,
        )

        created = await self._repo.create(invoice)

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.SYSTEM_CONFIG_UPDATED,
                actor_id=creator_id,
                ip_address=ip_address or "",
                metadata={
                    "action": "invoice_created",
                    "invoice_id": str(created.id),
                    "invoice_number": created.invoice_number,
                    "amount": str(created.amount),
                    "invoice_type": str(created.invoice_type),
                },
            )

        return created

    async def get_invoice(self, invoice_id: uuid.UUID) -> Invoice:
        invoice = await self._repo.get_by_id(invoice_id)
        if not invoice:
            raise NotFoundError(f"Invoice {invoice_id} not found.")
        return invoice

    async def list_invoices_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        *,
        status: InvoiceStatus | None = None,
        invoice_type: InvoiceType | None = None,
        billed_user_id: uuid.UUID | None = None,
        search_term: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> tuple[Sequence[Invoice], int]:
        return await self._repo.list_invoices_paginated(
            page,
            sort,
            status=status,
            invoice_type=invoice_type,
            billed_user_id=billed_user_id,
            search_term=search_term,
            start_date=start_date,
            end_date=end_date,
        )

    async def send_invoice(
        self,
        invoice_id: uuid.UUID,
        *,
        actor_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> Invoice:
        invoice = await self.get_invoice(invoice_id)

        if invoice.status not in (InvoiceStatus.DRAFT, InvoiceStatus.FAILED):
            raise ConflictError(f"Cannot send an invoice in {invoice.status.value} status.")

        # If payment gateway is available, generate hosted link
        if self._payment_gateway:
            expires_at = (
                datetime.combine(invoice.due_date, datetime.max.time(), tzinfo=UTC)
                if invoice.due_date
                else None
            )
            try:
                link = await self._payment_gateway.create_payment_link(
                    amount=float(invoice.amount),
                    currency=invoice.currency,
                    description=invoice.description,
                    reference_id=invoice.invoice_number,
                    recipient_name=invoice.billed_org_name or "Valued Client",
                    recipient_email=invoice.recipient_email,
                    recipient_phone=invoice.recipient_phone,
                    expires_at=expires_at,
                    notes={"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number},
                )
                invoice.payment_provider = link.provider
                invoice.payment_link_id = link.link_id
                invoice.payment_link_url = link.short_url
            except PaymentGatewayError as exc:
                logger.warning("Payment link creation failed for invoice %s: %s", invoice.id, exc)
                invoice.payment_provider = self._payment_gateway.provider_name
                invoice.payment_link_url = f"https://pay.pawguard.org/inv/{invoice.invoice_number}"
        else:
            invoice.payment_provider = "manual"
            invoice.payment_link_url = f"https://pay.pawguard.org/inv/{invoice.invoice_number}"

        invoice.status = InvoiceStatus.SENT
        await self._repo.update(invoice)

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.SYSTEM_CONFIG_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                metadata={
                    "action": "invoice_sent",
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number,
                    "link_url": invoice.payment_link_url,
                },
            )

        return invoice

    async def cancel_invoice(
        self,
        invoice_id: uuid.UUID,
        *,
        reason: str,
        actor_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> Invoice:
        invoice = await self.get_invoice(invoice_id)

        if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED):
            raise ConflictError(f"Cannot cancel an invoice that is already {invoice.status.value}.")

        if invoice.payment_link_id and self._payment_gateway:
            try:
                await self._payment_gateway.cancel_payment_link(link_id=invoice.payment_link_id)
            except Exception as exc:
                logger.warning(
                    "Failed to cancel payment link %s on gateway: %s", invoice.payment_link_id, exc
                )

        invoice.status = InvoiceStatus.CANCELLED
        invoice.cancellation_reason = reason
        await self._repo.update(invoice)

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.SYSTEM_CONFIG_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                metadata={
                    "action": "invoice_cancelled",
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number,
                    "reason": reason,
                },
            )

        return invoice

    async def resend_invoice(
        self,
        invoice_id: uuid.UUID,
        *,
        actor_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> Invoice:
        invoice = await self.get_invoice(invoice_id)

        if invoice.status != InvoiceStatus.SENT:
            raise ConflictError(
                f"Cannot resend an invoice in {invoice.status.value} status; must be sent."
            )

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.SYSTEM_CONFIG_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                metadata={
                    "action": "invoice_resent",
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number,
                },
            )

        return invoice

    async def manual_status_update(
        self,
        invoice_id: uuid.UUID,
        payload: InvoiceStatusUpdate,
        *,
        actor_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> Invoice:
        invoice = await self.get_invoice(invoice_id)

        invoice.status = payload.status
        if payload.status == InvoiceStatus.PAID:
            invoice.paid_at = payload.paid_at or datetime.now(UTC)
        if payload.notes:
            invoice.cancellation_reason = payload.notes

        await self._repo.update(invoice)

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.SYSTEM_CONFIG_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                metadata={
                    "action": "invoice_manual_status_update",
                    "invoice_id": str(invoice.id),
                    "new_status": payload.status.value,
                    "notes": payload.notes,
                },
            )

        return invoice

    async def process_webhook(self, event: WebhookEvent) -> bool:
        """Process incoming gateway payment link / invoice webhook events."""
        link_id = event.payment_link_id
        if not link_id and event.order_id:
            link_id = event.order_id

        invoice: Invoice | None = None
        if link_id:
            invoice = await self._repo.get_by_payment_link_id(link_id)

        if not invoice and event.raw_payload:
            # Check notes for invoice_number
            payload_data = event.raw_payload.get("payload", {})
            link_entity = payload_data.get("payment_link", {}).get("entity", {})
            notes = link_entity.get("notes", {})
            inv_num = notes.get("invoice_number")
            if inv_num:
                invoice = await self._repo.get_by_invoice_number(inv_num)

        if not invoice:
            logger.info("Webhook event %s did not match any invoice record.", event.event_type)
            return False

        if event.is_success or event.event_type in (
            "payment_link.paid",
            "invoice.paid",
            "payment.captured",
        ):
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = datetime.now(UTC)
            await self._repo.update(invoice)
            logger.info("Invoice %s marked PAID via webhook.", invoice.invoice_number)
            return True
        elif event.event_type in ("payment_link.expired", "payment_link.cancelled"):
            if invoice.status == InvoiceStatus.SENT:
                invoice.status = InvoiceStatus.FAILED
                await self._repo.update(invoice)
                logger.info(
                    "Invoice %s marked FAILED via webhook (%s).",
                    invoice.invoice_number,
                    event.event_type,
                )
                return True

        return False

    async def sweep_overdue_invoices(self, as_of_date: date | None = None) -> int:
        target_date = as_of_date or datetime.now(UTC).date()
        overdue_invoices = await self._repo.list_overdue_candidates(target_date)

        count = 0
        for inv in overdue_invoices:
            inv.status = InvoiceStatus.OVERDUE
            await self._repo.update(inv)
            count += 1

        logger.info("Swept %d invoices into OVERDUE status as of %s.", count, target_date)
        return count

    async def generate_receipt_pdf(self, invoice_id: uuid.UUID) -> bytes:
        invoice = await self.get_invoice(invoice_id)
        if invoice.status != InvoiceStatus.PAID:
            raise ValidationFailedError(
                f"Receipt is only available for paid invoices; current status is {invoice.status.value}."
            )

        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas

            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=letter)
            c.setFont("Helvetica-Bold", 20)
            c.drawString(50, 750, "PAWGUARD INVOICE RECEIPT")

            c.setFont("Helvetica", 10)
            c.drawString(
                50,
                730,
                f"Receipt Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            )
            c.drawString(50, 715, "Status: PAID IN FULL")

            c.setLineWidth(1)
            c.line(50, 705, 550, 705)

            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, 680, f"Invoice Number: {invoice.invoice_number}")
            c.setFont("Helvetica", 11)
            c.drawString(
                50, 660, f"Invoice Type: {invoice.invoice_type.value.replace('_', ' ').title()}"
            )
            c.drawString(
                50, 640, f"Billed To: {invoice.billed_org_name or invoice.recipient_email or 'N/A'}"
            )
            if invoice.recipient_email:
                c.drawString(50, 620, f"Email: {invoice.recipient_email}")
            if invoice.recipient_phone:
                c.drawString(50, 600, f"Phone: {invoice.recipient_phone}")

            c.line(50, 585, 550, 585)

            c.drawString(50, 560, f"Description: {invoice.description}")
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, 530, f"Total Amount Paid: {invoice.currency} {invoice.amount:,.2f}")
            c.setFont("Helvetica", 10)
            paid_str = (
                invoice.paid_at.strftime("%Y-%m-%d %H:%M:%S UTC") if invoice.paid_at else "Verified"
            )
            c.drawString(50, 510, f"Paid At: {paid_str}")
            if invoice.payment_provider:
                c.drawString(50, 495, f"Payment Provider: {invoice.payment_provider.title()}")

            c.drawString(
                50, 100, "PawGuard Platform Services — Official Electronic Payment Receipt"
            )
            c.save()
            buf.seek(0)
            return buf.getvalue()
        except ImportError:
            # Fallback simple text receipt
            receipt_text = f"""PAWGUARD INVOICE RECEIPT
Invoice Number: {invoice.invoice_number}
Status: PAID
Amount: {invoice.currency} {invoice.amount}
Billed To: {invoice.billed_org_name or invoice.recipient_email}
Description: {invoice.description}
Paid At: {invoice.paid_at}
"""
            return receipt_text.encode("utf-8")
