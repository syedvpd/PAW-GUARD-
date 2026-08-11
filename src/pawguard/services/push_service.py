"""Push notification service using Firebase Cloud Messaging (FCM).

Gracefully degrades when Firebase credentials are not configured:
all public methods return silently instead of raising, so the rest
of the notification pipeline (in-app + email) continues to work.
"""

import uuid
from typing import Any

from pawguard.core.config import get_settings
from pawguard.core.logging import get_logger

logger = get_logger(__name__)

_firebase_initialized = False
_firebase_app: Any = None


def _get_firebase_app() -> Any:
    """Lazy-initialize the Firebase Admin SDK once per process."""
    global _firebase_initialized, _firebase_app  # noqa: PLW0603
    if _firebase_initialized:
        return _firebase_app

    settings = get_settings()
    fcm_credentials_path = getattr(settings, "fcm_credentials_path", "")
    if not fcm_credentials_path:
        logger.debug("fcm_not_configured")
        _firebase_initialized = True
        return None

    try:
        import firebase_admin  # type: ignore[import-untyped]

        cred = firebase_admin.Credentials.Cert(fcm_credentials_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("fcm_initialized")
        return _firebase_app
    except Exception as exc:
        logger.warning("fcm_init_failed", error=str(exc))
        _firebase_initialized = True
        return None


async def send_push_notification(
    fcm_token: str,
    *,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    user_id: uuid.UUID | None = None,
) -> bool:
    """Send a push notification to a single device via FCM.

    Returns True if the message was accepted by FCM, False otherwise.
    Never raises - push delivery failures must not block the notification
    pipeline (in-app + email).
    """
    app = _get_firebase_app()
    if app is None:
        return False

    try:
        from firebase_admin import messaging  # type: ignore[import-untyped]

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=fcm_token,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", badge=1)
                )
            ),
        )
        response = messaging.send(message, app=app)
        logger.debug(
            "push_sent",
            message_id=response,
            user_id=str(user_id) if user_id else None,
        )
        return True
    except Exception as exc:
        logger.warning(
            "push_send_failed",
            error=str(exc),
            user_id=str(user_id) if user_id else None,
        )
        return False


async def send_push_notification_to_users(
    user_tokens: list[tuple[uuid.UUID, str]],
    *,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> int:
    """Send the same push notification to multiple devices.

    ``user_tokens`` is a list of (user_id, fcm_token) tuples.
    Returns the count of successfully sent messages.
    """
    app = _get_firebase_app()
    if app is None:
        return 0

    sent = 0
    for user_id, fcm_token in user_tokens:
        if not fcm_token:
            continue
        ok = await send_push_notification(
            fcm_token,
            title=title,
            body=body,
            data=data,
            user_id=user_id,
        )
        if ok:
            sent += 1
    return sent
