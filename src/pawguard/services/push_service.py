import asyncio
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
    fcm_credentials_json = getattr(settings, "fcm_credentials_json", "")

    if not fcm_credentials_path and not fcm_credentials_json:
        logger.debug("fcm_not_configured")
        _firebase_initialized = True
        return None

    try:
        import json

        import firebase_admin  # type: ignore[import-untyped]
        from firebase_admin import credentials  # type: ignore[import-untyped]

        if fcm_credentials_json:
            cred_dict = json.loads(fcm_credentials_json) if isinstance(fcm_credentials_json, str) else fcm_credentials_json
            cred = credentials.Certificate(cred_dict)
        else:
            cred = credentials.Certificate(fcm_credentials_path)

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
        response = await asyncio.to_thread(messaging.send, message, app=app)
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
    max_concurrency: int = 10,
) -> int:
    """Send the same push notification to multiple devices concurrently.

    ``user_tokens`` is a list of (user_id, fcm_token) tuples.
    Returns the count of successfully sent messages.
    """
    app = _get_firebase_app()
    if app is None:
        return 0

    valid_tokens = [(uid, tok) for uid, tok in user_tokens if tok]
    if not valid_tokens:
        return 0

    sem = asyncio.Semaphore(max_concurrency)

    async def _send_one(uid: uuid.UUID, tok: str) -> bool:
        async with sem:
            return await send_push_notification(
                tok, title=title, body=body, data=data, user_id=uid
            )

    results = await asyncio.gather(
        *[_send_one(uid, tok) for uid, tok in valid_tokens],
        return_exceptions=True,
    )
    return sum(1 for r in results if r is True)
