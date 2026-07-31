"""Razorpay adapter for the PaymentGateway contract."""

import hashlib
import hmac
import json
from typing import Any

import razorpay

from pawguard.core.payments.base import (
    PaymentGateway,
    PaymentGatewayError,
    PaymentOrder,
    PaymentVerificationResult,
    WebhookEvent,
)


class RazorpayGateway(PaymentGateway):
    provider_name = "razorpay"

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str) -> None:
        if not key_id or not key_secret:
            raise PaymentGatewayError(
                "Razorpay is not configured: set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET."
            )
        self._key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret
        self._client = razorpay.Client(auth=(key_id, key_secret))

    async def create_order(
        self, *, amount: float, currency: str, receipt: str, notes: dict[str, str] | None = None
    ) -> PaymentOrder:
        # Razorpay expects the smallest currency unit (e.g. paise for INR).
        amount_subunits = int(round(amount * 100))
        try:
            order: dict[str, Any] = self._client.order.create(
                {
                    "amount": amount_subunits,
                    "currency": currency.upper(),
                    "receipt": receipt,
                    "notes": notes or {},
                }
            )
        except Exception as exc:  # razorpay raises provider-specific errors
            raise PaymentGatewayError(f"Razorpay order creation failed: {exc}") from exc

        return PaymentOrder(
            provider=self.provider_name,
            order_id=order["id"],
            amount=amount,
            currency=currency.upper(),
            checkout_key=self._key_id,
            receipt=receipt,
        )

    def verify_payment_signature(
        self, *, order_id: str, payment_id: str, signature: str
    ) -> PaymentVerificationResult:
        try:
            self._client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
        except razorpay.errors.SignatureVerificationError as exc:
            return PaymentVerificationResult(
                verified=False, order_id=order_id, failure_reason=str(exc)
            )
        return PaymentVerificationResult(
            verified=True, payment_id=payment_id, order_id=order_id
        )

    def parse_webhook(self, *, payload: bytes, signature: str) -> WebhookEvent:
        if not self._webhook_secret:
            raise PaymentGatewayError("RAZORPAY_WEBHOOK_SECRET is not configured.")

        expected = hmac.new(
            self._webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise PaymentGatewayError("Invalid Razorpay webhook signature.")

        body = json.loads(payload)
        event_type = body.get("event", "")
        payment_entity = body.get("payload", {}).get("payment", {}).get("entity", {})

        return WebhookEvent(
            event_type=event_type,
            order_id=payment_entity.get("order_id"),
            payment_id=payment_entity.get("id"),
            is_success=event_type == "payment.captured",
            raw_payload=body,
        )
