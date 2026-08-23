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
            cred_dict = (
                json.loads(fcm_credentials_json)
                if isinstance(fcm_credentials_json, str)
                else fcm_credentials_json
            )
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

    import time

    from pawguard.core.metrics import track_outbound_request

    start = time.perf_counter()
    req_size = len(title) + len(body) + len(str(data or {}))

    try:
        from firebase_admin import messaging  # type: ignore[import-untyped]

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=fcm_token,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(aps=messaging.Aps(sound="default", badge=1))
            ),
        )
        response = await asyncio.to_thread(messaging.send, message, app=app)
        duration_ms = (time.perf_counter() - start) * 1000
        track_outbound_request(
            destination="fcm",
            operation="send_message",
            request_bytes=req_size,
            response_bytes=len(str(response)),
            duration_ms=duration_ms,
            status="success",
        )
        logger.debug(
            "push_sent",
            message_id=response,
            user_id=str(user_id) if user_id else None,
        )
        return True
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        track_outbound_request(
            destination="fcm",
            operation="send_message",
            request_bytes=req_size,
            response_bytes=0,
            duration_ms=duration_ms,
            status="failed",
        )
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
    """Send the same push notification to multiple devices concurrently using FCM Multicast API.

    Deduplicates tokens, handles chunks of 500, and cleans up unregistered tokens in the database.
    """
    app = _get_firebase_app()
    if app is None:
        return 0

    # 1. Deduplicate tokens and filter out empty ones
    seen_tokens = set()
    deduped_tokens: list[tuple[uuid.UUID, str]] = []
    for uid, tok in user_tokens:
        if tok and tok not in seen_tokens:
            seen_tokens.add(tok)
            deduped_tokens.append((uid, tok))

    if not deduped_tokens:
        return 0

    from firebase_admin import messaging

    success_count = 0
    chunk_size = 500
    unregistered_uids: list[uuid.UUID] = []

    for i in range(0, len(deduped_tokens), chunk_size):
        chunk = deduped_tokens[i : i + chunk_size]
        tokens_only = [tok for _, tok in chunk]

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            tokens=tokens_only,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(aps=messaging.Aps(sound="default", badge=1))
            ),
        )

        import time

        from pawguard.core.metrics import track_outbound_request

        start = time.perf_counter()
        req_size = (len(title) + len(body) + len(str(data or {}))) * len(tokens_only)

        try:
            response = await asyncio.to_thread(messaging.send_multicast, message, app=app)
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="fcm",
                operation="send_multicast",
                request_bytes=req_size,
                response_bytes=100 * len(response.responses),
                duration_ms=duration_ms,
                status="success",
            )
            success_count += response.success_count

            # Find unregistered tokens to clean up
            if response.failure_count > 0:
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                        # Unregistered tokens fail with unregistered error code
                        if (
                            getattr(resp, "exception", None)
                            and "unregistered" in str(resp.exception).lower()
                        ) or (
                            getattr(resp, "error", None)
                            and getattr(resp.error, "code", None) == "unregistered"
                        ):
                            unregistered_uids.append(chunk[idx][0])
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="fcm",
                operation="send_multicast",
                request_bytes=req_size,
                response_bytes=0,
                duration_ms=duration_ms,
                status="failed",
            )
            logger.warning("fcm_multicast_chunk_failed", error=str(exc))

    # Clean up unregistered tokens in a background task to avoid blocking the HTTP pipeline/workers
    if unregistered_uids:

        async def _cleanup_unregistered():
            try:
                from sqlalchemy import update

                from pawguard.db.session import AsyncSessionLocal
                from pawguard.modules.auth.models import User

                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(User).where(User.id.in_(unregistered_uids)).values(fcm_token=None)
                    )
                    await session.commit()
                    logger.info("cleaned_unregistered_fcm_tokens", count=len(unregistered_uids))
            except Exception as e:
                logger.warning("fcm_cleanup_failed", error=str(e))

        asyncio.create_task(_cleanup_unregistered())

    return success_count
