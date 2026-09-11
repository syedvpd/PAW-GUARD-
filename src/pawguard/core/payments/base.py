"""Provider-agnostic payment gateway contract.

Every payment provider (Razorpay today, Stripe/PayPal tomorrow) implements this
interface. Business code (DonationService) only ever talks to `PaymentGateway`,
so swapping providers means writing one new adapter and flipping a config value
- no changes to services, routers, or schemas.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PaymentOrder:
    """A provider-created payment intent, handed back to the client to complete checkout."""

    provider: str
    order_id: str
    amount: float
    currency: str
    checkout_key: str
    receipt: str


@dataclass(frozen=True)
class PaymentLink:
    """A provider-created hosted payment link sent to external parties without app-side checkout."""

    provider: str
    link_id: str
    short_url: str
    amount: float
    currency: str
    status: str
    expires_at: datetime | None = None


@dataclass(frozen=True)
class PaymentVerificationResult:
    verified: bool
    payment_id: str | None = None
    order_id: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class WebhookEvent:
    event_type: str
    order_id: str | None
    payment_id: str | None
    is_success: bool
    raw_payload: dict[str, object]
    payment_link_id: str | None = None


class PaymentGateway(ABC):
    """Contract for a payment provider adapter."""

    provider_name: str

    @abstractmethod
    async def create_order(
        self, *, amount: float, currency: str, receipt: str, notes: dict[str, str] | None = None
    ) -> PaymentOrder:
        """Create a payment intent/order with the provider ahead of client-side checkout."""

    @abstractmethod
    async def create_payment_link(
        self,
        *,
        amount: float,
        currency: str,
        description: str,
        reference_id: str,
        recipient_name: str | None = None,
        recipient_email: str | None = None,
        recipient_phone: str | None = None,
        expires_at: datetime | None = None,
        notes: dict[str, str] | None = None,
    ) -> PaymentLink:
        """Create a hosted payment link for a party without app-side checkout."""

    @abstractmethod
    async def cancel_payment_link(self, *, link_id: str) -> None:
        """Void an unpaid link (e.g. invoice cancelled before payment)."""

    @abstractmethod
    def verify_payment_signature(
        self, *, order_id: str, payment_id: str, signature: str
    ) -> PaymentVerificationResult:
        """Verify the signature returned by the provider's checkout callback."""

    @abstractmethod
    def parse_webhook(self, *, payload: bytes, signature: str) -> WebhookEvent:
        """Verify a webhook's signature and parse it into a normalised event."""


class PaymentGatewayError(Exception):
    """Raised when a provider call fails or a signature cannot be verified."""
