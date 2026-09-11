"""Unit tests for Invoicing & Service Fee Collection module."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pawguard.core.exceptions import ConflictError, ValidationFailedError
from pawguard.core.payments.base import PaymentGateway, PaymentLink, WebhookEvent
from pawguard.modules.invoice.models import Invoice, InvoiceStatus, InvoiceType
from pawguard.modules.invoice.repository import InvoiceRepository
from pawguard.modules.invoice.schemas import (
    InvoiceCreate,
)
from pawguard.modules.invoice.service import InvoiceService


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_repo(mock_session):
    return InvoiceRepository(mock_session)


@pytest.fixture
def mock_gateway():
    gateway = AsyncMock(spec=PaymentGateway)
    gateway.provider_name = "razorpay"
    gateway.create_payment_link = AsyncMock(
        return_value=PaymentLink(
            provider="razorpay",
            link_id="plink_12345",
            short_url="https://rzp.io/i/abcdef",
            amount=1500.00,
            currency="INR",
            status="created",
        )
    )
    gateway.cancel_payment_link = AsyncMock()
    return gateway


@pytest.fixture
def invoice_service(mock_repo, mock_gateway):
    return InvoiceService(
        repository=mock_repo,
        payment_gateway=mock_gateway,
    )


class TestInvoiceService:
    @pytest.mark.asyncio
    async def test_create_draft_invoice_success(self, invoice_service, mock_repo):
        creator_id = uuid.uuid4()
        payload = InvoiceCreate(
            invoice_type=InvoiceType.PARTNER_BILLING,
            amount=Decimal("2500.00"),
            currency="INR",
            description="Monthly shelter facility commission",
            due_date=date(2026, 8, 31),
            billed_org_name="City Animal Shelter",
            recipient_email="billing@cityshelter.org",
            recipient_phone="+91-9876543210",
        )

        with patch.object(
            mock_repo, "get_next_invoice_number", AsyncMock(return_value="INV-2026-0001")
        ):
            invoice = await invoice_service.create_draft_invoice(payload, creator_id=creator_id)

            assert invoice.invoice_number == "INV-2026-0001"
            assert invoice.status == InvoiceStatus.DRAFT
            assert invoice.amount == Decimal("2500.00")
            assert invoice.currency == "INR"
            assert invoice.billed_org_name == "City Animal Shelter"
            assert invoice.recipient_email == "billing@cityshelter.org"
            assert invoice.created_by_id == creator_id

    @pytest.mark.asyncio
    async def test_send_invoice_issues_payment_link(self, invoice_service, mock_repo, mock_gateway):
        invoice_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        inv = Invoice(
            id=invoice_id,
            invoice_number="INV-2026-0001",
            invoice_type=InvoiceType.PARTNER_BILLING,
            status=InvoiceStatus.DRAFT,
            amount=Decimal("1500.00"),
            currency="INR",
            description="Commission fee",
            billed_org_name="Partner Clinic",
            recipient_email="admin@clinic.com",
            created_by_id=actor_id,
        )

        with patch.object(mock_repo, "get_by_id", AsyncMock(return_value=inv)):
            sent_inv = await invoice_service.send_invoice(invoice_id, actor_id=actor_id)

            assert sent_inv.status == InvoiceStatus.SENT
            assert sent_inv.payment_link_id == "plink_12345"
            assert sent_inv.payment_link_url == "https://rzp.io/i/abcdef"
            assert sent_inv.payment_provider == "razorpay"
            mock_gateway.create_payment_link.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_invoice_already_paid_fails(self, invoice_service, mock_repo):
        invoice_id = uuid.uuid4()
        inv = Invoice(
            id=invoice_id,
            invoice_number="INV-2026-0001",
            invoice_type=InvoiceType.PARTNER_BILLING,
            status=InvoiceStatus.PAID,
            amount=Decimal("1500.00"),
            currency="INR",
            description="Fee",
            created_by_id=uuid.uuid4(),
        )

        with (
            patch.object(mock_repo, "get_by_id", AsyncMock(return_value=inv)),
            pytest.raises(ConflictError, match="Cannot send an invoice"),
        ):
            await invoice_service.send_invoice(invoice_id, actor_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_invoice_voids_gateway_link(
        self, invoice_service, mock_repo, mock_gateway
    ):
        invoice_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        inv = Invoice(
            id=invoice_id,
            invoice_number="INV-2026-0001",
            invoice_type=InvoiceType.PARTNER_BILLING,
            status=InvoiceStatus.SENT,
            amount=Decimal("1500.00"),
            currency="INR",
            description="Fee",
            payment_link_id="plink_12345",
            created_by_id=actor_id,
        )

        with patch.object(mock_repo, "get_by_id", AsyncMock(return_value=inv)):
            cancelled = await invoice_service.cancel_invoice(
                invoice_id, reason="Client negotiated waiver", actor_id=actor_id
            )

            assert cancelled.status == InvoiceStatus.CANCELLED
            assert cancelled.cancellation_reason == "Client negotiated waiver"
            mock_gateway.cancel_payment_link.assert_called_once_with(link_id="plink_12345")

    @pytest.mark.asyncio
    async def test_webhook_payment_link_paid_marks_invoice_paid(self, invoice_service, mock_repo):
        invoice_id = uuid.uuid4()
        inv = Invoice(
            id=invoice_id,
            invoice_number="INV-2026-0001",
            invoice_type=InvoiceType.PARTNER_BILLING,
            status=InvoiceStatus.SENT,
            amount=Decimal("1500.00"),
            currency="INR",
            description="Fee",
            payment_link_id="plink_9999",
            created_by_id=uuid.uuid4(),
        )

        with patch.object(mock_repo, "get_by_payment_link_id", AsyncMock(return_value=inv)):
            event = WebhookEvent(
                event_type="payment_link.paid",
                order_id=None,
                payment_id="pay_8888",
                is_success=True,
                raw_payload={},
                payment_link_id="plink_9999",
            )
            processed = await invoice_service.process_webhook(event)
            assert processed is True
            assert inv.status == InvoiceStatus.PAID
            assert inv.paid_at is not None

    @pytest.mark.asyncio
    async def test_sweep_overdue_invoices(self, invoice_service, mock_repo):
        overdue_inv = Invoice(
            id=uuid.uuid4(),
            invoice_number="INV-2026-0001",
            invoice_type=InvoiceType.PARTNER_BILLING,
            status=InvoiceStatus.SENT,
            amount=Decimal("1500.00"),
            currency="INR",
            description="Fee",
            due_date=date(2026, 7, 1),
            created_by_id=uuid.uuid4(),
        )

        with patch.object(
            mock_repo, "list_overdue_candidates", AsyncMock(return_value=[overdue_inv])
        ):
            count = await invoice_service.sweep_overdue_invoices(as_of_date=date(2026, 8, 1))
            assert count == 1
            assert overdue_inv.status == InvoiceStatus.OVERDUE

    @pytest.mark.asyncio
    async def test_generate_receipt_pdf_success_for_paid(self, invoice_service, mock_repo):
        invoice_id = uuid.uuid4()
        inv = Invoice(
            id=invoice_id,
            invoice_number="INV-2026-0001",
            invoice_type=InvoiceType.SERVICE_FEE,
            status=InvoiceStatus.PAID,
            amount=Decimal("350.00"),
            currency="INR",
            description="Adoption platform service fee",
            billed_org_name="Jane Adopter",
            recipient_email="jane@example.com",
            paid_at=datetime.now(UTC),
            payment_provider="razorpay",
            created_by_id=uuid.uuid4(),
        )

        with patch.object(mock_repo, "get_by_id", AsyncMock(return_value=inv)):
            receipt = await invoice_service.generate_receipt_pdf(invoice_id)
            assert isinstance(receipt, bytes)
            assert len(receipt) > 0

    @pytest.mark.asyncio
    async def test_generate_receipt_pdf_fails_for_unpaid(self, invoice_service, mock_repo):
        invoice_id = uuid.uuid4()
        inv = Invoice(
            id=invoice_id,
            invoice_number="INV-2026-0001",
            invoice_type=InvoiceType.SERVICE_FEE,
            status=InvoiceStatus.DRAFT,
            amount=Decimal("350.00"),
            currency="INR",
            description="Adoption fee",
            created_by_id=uuid.uuid4(),
        )

        with (
            patch.object(mock_repo, "get_by_id", AsyncMock(return_value=inv)),
            pytest.raises(ValidationFailedError, match="only available for paid"),
        ):
            await invoice_service.generate_receipt_pdf(invoice_id)
