"""Payment gateway factory. Swap providers via the PAYMENT_PROVIDER setting."""

from functools import lru_cache

from pawguard.core.config import get_settings
from pawguard.core.payments.base import (
    PaymentGateway,
    PaymentGatewayError,
    PaymentOrder,
    PaymentVerificationResult,
    WebhookEvent,
)

__all__ = [
    "PaymentGateway",
    "PaymentGatewayError",
    "PaymentOrder",
    "PaymentVerificationResult",
    "WebhookEvent",
    "get_payment_gateway",
]


@lru_cache
def get_payment_gateway() -> PaymentGateway:
    settings = get_settings()
    provider = settings.payment_provider.lower()

    if provider == "razorpay":
        from pawguard.core.payments.razorpay_gateway import RazorpayGateway

        return RazorpayGateway(
            key_id=settings.razorpay_key_id,
            key_secret=settings.razorpay_key_secret,
            webhook_secret=settings.razorpay_webhook_secret,
        )

    raise PaymentGatewayError(f"Unsupported payment provider configured: {provider!r}")
