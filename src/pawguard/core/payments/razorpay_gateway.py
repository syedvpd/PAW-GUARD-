"""Razorpay adapter for the PaymentGateway contract."""

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

import razorpay

from pawguard.core.payments.base import (
    PaymentGateway,
    PaymentGatewayError,
    PaymentLink,
    PaymentOrder,
    PaymentVerificationResult,
    WebhookEvent,
)
from pawguard.core.resilience import CircuitBreaker, CircuitBreakerOpenException

razorpay_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)


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
        import time

        from pawguard.core.metrics import track_outbound_request

        start = time.perf_counter()
        # Razorpay expects the smallest currency unit (e.g. paise for INR).
        amount_subunits = int(round(amount * 100))
        payload_data = {
            "amount": amount_subunits,
            "currency": currency.upper(),
            "receipt": receipt,
            "notes": notes or {},
        }
        req_bytes = len(json.dumps(payload_data))
        try:

            @razorpay_breaker
            async def _create():
                return self._client.order.create(payload_data)

            order: dict[str, Any] = await _create()
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="razorpay",
                operation="create_order",
                request_bytes=req_bytes,
                response_bytes=len(json.dumps(order)),
                duration_ms=duration_ms,
                status="success",
            )
        except CircuitBreakerOpenException as exc:
            raise PaymentGatewayError(f"Payment gateway is temporarily unavailable: {exc}") from exc
        except Exception as exc:  # razorpay raises provider-specific errors
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="razorpay",
                operation="create_order",
                request_bytes=req_bytes,
                response_bytes=0,
                duration_ms=duration_ms,
                status="failed",
            )
            raise PaymentGatewayError(f"Razorpay order creation failed: {exc}") from exc

        return PaymentOrder(
            provider=self.provider_name,
            order_id=order["id"],
            amount=amount,
            currency=currency.upper(),
            checkout_key=self._key_id,
            receipt=receipt,
        )

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
        import time

        from pawguard.core.metrics import track_outbound_request

        start = time.perf_counter()
        amount_subunits = int(round(amount * 100))

        customer_dict: dict[str, str] = {}
        if recipient_name:
            customer_dict["name"] = recipient_name
        if recipient_email:
            customer_dict["email"] = recipient_email
        if recipient_phone:
            customer_dict["contact"] = recipient_phone

        payload_data: dict[str, Any] = {
            "amount": amount_subunits,
            "currency": currency.upper(),
            "description": description,
            "reference_id": reference_id,
            "customer": customer_dict,
            "notify": {"sms": bool(recipient_phone), "email": bool(recipient_email)},
            "reminder_enable": True,
            "notes": notes or {},
        }
        if expires_at:
            payload_data["expire_by"] = int(expires_at.timestamp())

        req_bytes = len(json.dumps(payload_data))
        try:

            @razorpay_breaker
            async def _create_link():
                return self._client.payment_link.create(payload_data)

            link: dict[str, Any] = await _create_link()
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="razorpay",
                operation="create_payment_link",
                request_bytes=req_bytes,
                response_bytes=len(json.dumps(link)),
                duration_ms=duration_ms,
                status="success",
            )
        except CircuitBreakerOpenException as exc:
            raise PaymentGatewayError(f"Payment gateway is temporarily unavailable: {exc}") from exc
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="razorpay",
                operation="create_payment_link",
                request_bytes=req_bytes,
                response_bytes=0,
                duration_ms=duration_ms,
                status="failed",
            )
            raise PaymentGatewayError(f"Razorpay payment link creation failed: {exc}") from exc

        return PaymentLink(
            provider=self.provider_name,
            link_id=link.get("id", ""),
            short_url=link.get("short_url", ""),
            amount=amount,
            currency=currency.upper(),
            status=link.get("status", "created"),
            expires_at=expires_at,
        )

    async def cancel_payment_link(self, *, link_id: str) -> None:
        import time

        from pawguard.core.metrics import track_outbound_request

        start = time.perf_counter()
        try:

            @razorpay_breaker
            async def _cancel():
                return self._client.payment_link.cancel(link_id)

            await _cancel()
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="razorpay",
                operation="cancel_payment_link",
                request_bytes=0,
                response_bytes=0,
                duration_ms=duration_ms,
                status="success",
            )
        except CircuitBreakerOpenException as exc:
            raise PaymentGatewayError(f"Payment gateway is temporarily unavailable: {exc}") from exc
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="razorpay",
                operation="cancel_payment_link",
                request_bytes=0,
                response_bytes=0,
                duration_ms=duration_ms,
                status="failed",
            )
            raise PaymentGatewayError(f"Razorpay payment link cancellation failed: {exc}") from exc

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
        return PaymentVerificationResult(verified=True, payment_id=payment_id, order_id=order_id)

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
        payload_data = body.get("payload", {})
        payment_entity = payload_data.get("payment", {}).get("entity", {})
        order_entity = payload_data.get("order", {}).get("entity", {})
        link_entity = payload_data.get("payment_link", {}).get("entity", {})

        order_id = payment_entity.get("order_id") or order_entity.get("id")
        payment_id = payment_entity.get("id") or order_entity.get("payment_id")
        payment_link_id = link_entity.get("id") or payment_entity.get("payment_link_id")

        is_success = event_type in (
            "payment.captured",
            "order.paid",
            "payment_link.paid",
            "invoice.paid",
        )

        return WebhookEvent(
            event_type=event_type,
            order_id=order_id,
            payment_id=payment_id,
            is_success=is_success,
            raw_payload=body,
            payment_link_id=payment_link_id,
        )
