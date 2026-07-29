"""Notification dispatch interface. Push/SMS backends are wired in a later phase.

This exists now so auth (and future modules) can depend on a stable contract without
being redesigned when FCM/SMS providers are integrated.
"""

from typing import Protocol


class NotificationService(Protocol):
    async def send_push(self, *, user_id: str, title: str, body: str) -> None: ...

    async def send_sms(self, *, phone: str, message: str) -> None: ...


class NoopNotificationService:
    """Default implementation until FCM/SMS providers are integrated."""

    async def send_push(self, *, user_id: str, title: str, body: str) -> None:
        return None

    async def send_sms(self, *, phone: str, message: str) -> None:
        return None
