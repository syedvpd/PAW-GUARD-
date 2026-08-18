"""Test Firebase Cloud Messaging configuration and connectivity.

Usage:
    python -m scripts.test_fcm                     # Check config only
    python -m scripts.test_fcm --send <fcm_token>  # Send test push to device
    python -m scripts.test_fcm --send-all           # Send to all registered tokens

Requires FCM_CREDENTIALS_JSON (raw JSON string) or FCM_CREDENTIALS_PATH (file path)
to be set in the environment.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# Add src to path so we can import pawguard
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def check_config() -> dict:
    """Check FCM configuration status."""
    from pawguard.core.config import get_settings

    settings = get_settings()
    result = {
        "fcm_credentials_path": bool(settings.fcm_credentials_path),
        "fcm_credentials_json": bool(settings.fcm_credentials_json),
        "path_value": settings.fcm_credentials_path[:50] + "..." if settings.fcm_credentials_path else "",
        "json_length": len(settings.fcm_credentials_json) if settings.fcm_credentials_json else 0,
    }

    print("=" * 60)
    print("FCM Configuration Check")
    print("=" * 60)
    print(f"  FCM_CREDENTIALS_PATH set: {result['fcm_credentials_path']}")
    if result["fcm_credentials_path"]:
        print(f"  Path value: {result['path_value']}")
    print(f"  FCM_CREDENTIALS_JSON set: {result['fcm_credentials_json']}")
    if result["fcm_credentials_json"]:
        print(f"  JSON length: {result['json_length']} chars")
        # Validate JSON structure
        try:
            cred_dict = json.loads(settings.fcm_credentials_json)
            required_keys = ["type", "project_id", "private_key", "client_email"]
            missing = [k for k in required_keys if k not in cred_dict]
            if missing:
                print(f"  WARNING: Missing keys in JSON: {missing}")
                result["valid_json"] = False
            else:
                print(f"  JSON structure: VALID (project_id: {cred_dict.get('project_id', 'N/A')})")
                result["valid_json"] = True
        except json.JSONDecodeError as e:
            print(f"  ERROR: Invalid JSON: {e}")
            result["valid_json"] = False
    else:
        result["valid_json"] = False

    if not result["fcm_credentials_path"] and not result["fcm_credentials_json"]:
        print("\n  STATUS: NOT CONFIGURED - Push notifications will silently degrade")
        print("  FIX: Set FCM_CREDENTIALS_JSON in Render environment with the service account JSON")
    elif result.get("valid_json") is False and result["fcm_credentials_json"]:
        print("\n  STATUS: INVALID JSON - Fix the FCM_CREDENTIALS_JSON value")
    else:
        print("\n  STATUS: CONFIGURED")

    print("=" * 60)
    return result


def test_firebase_init() -> bool:
    """Test Firebase Admin SDK initialization."""
    print("\nTesting Firebase Admin SDK initialization...")

    from pawguard.services.push_service import _get_firebase_app

    app = _get_firebase_app()
    if app is None:
        print("  FAILED: Firebase app is None (credentials not configured or invalid)")
        return False

    print(f"  SUCCESS: Firebase app initialized (project: {app.project_id})")
    return True


async def send_test_push(fcm_token: str) -> bool:
    """Send a test push notification to a single device."""
    from pawguard.services.push_service import send_push_notification

    print(f"\nSending test push to token: {fcm_token[:20]}...")

    result = await send_push_notification(
        fcm_token,
        title="PawGuard Test Push",
        body="If you see this, FCM is working correctly!",
        data={"action_url": "/test", "type": "test"},
        user_id=uuid.uuid4(),
    )

    if result:
        print("  SUCCESS: Push notification accepted by FCM")
    else:
        print("  FAILED: Push notification rejected (check logs for details)")
    return result


async def send_to_all_registered() -> int:
    """Send test push to all users with FCM tokens."""
    from sqlalchemy import select

    from pawguard.db.session import AsyncSessionLocal
    from pawguard.modules.auth.models import User
    from pawguard.services.push_service import send_push_notification_to_users

    print("\nFetching all users with FCM tokens...")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User.id, User.fcm_token).where(
                User.fcm_token.isnot(None),
                User.fcm_token != "",
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        rows = result.all()

    if not rows:
        print("  No users with FCM tokens found")
        return 0

    print(f"  Found {len(rows)} users with FCM tokens")

    tokens = [(row[0], row[1]) for row in rows]
    sent = await send_push_notification_to_users(
        tokens,
        title="PawGuard Test Push",
        body="This is a test notification from the backend team.",
        data={"action_url": "/test", "type": "test"},
    )

    print(f"  Successfully sent to {sent}/{len(rows)} devices")
    return sent


def main():
    parser = argparse.ArgumentParser(description="Test FCM configuration")
    parser.add_argument("--send", type=str, help="FCM token to send test push to")
    parser.add_argument("--send-all", action="store_true", help="Send to all registered tokens")
    parser.add_argument("--init-only", action="store_true", help="Only check config and init")
    args = parser.parse_args()

    # Step 1: Check config
    check_config()

    # Step 2: Test init
    if not test_firebase_init():
        sys.exit(1)

    if args.init_only:
        sys.exit(0)

    # Step 3: Send test
    if args.send:
        asyncio.run(send_test_push(args.send))
    elif args.send_all:
        asyncio.run(send_to_all_registered())
    else:
        print("\nNo send action specified. Use --send <token> or --send-all")
        print("Or run with --init-only to just check configuration")


if __name__ == "__main__":
    main()
