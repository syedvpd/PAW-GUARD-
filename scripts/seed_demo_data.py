"""Seed test notifications and success stories for the frontend.

Usage:
    uv run python scripts/seed_demo_data.py
"""

import asyncio
import sys
import uuid
from pathlib import Path
from datetime import datetime, UTC

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth.models import User, Role, Permission
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.rescue.models import RescueRequest
from pawguard.modules.shelter.models import ShelterFacility, ShelterSection, Kennel
from pawguard.modules.foster.models import FosterProfile
from pawguard.modules.notifications.models import Notification
from pawguard.modules.portal.models import SuccessStory, ContentStatus

NOTIFICATIONS_DATA = [
    {
        "title": "Welcome to PawGuard!",
        "body": "Your test account has been successfully set up. Explore the dashboard to manage rescues, medical logs, and adoptions.",
        "notification_type": "general",
    },
    {
        "title": "Emergency Dispatch Request",
        "body": "New emergency rescue case RC-0012 has been reported near Sector 62. Check your assigned cases for details.",
        "notification_type": "rescue",
        "action_url": "/dashboard/rescue/cases",
    },
    {
        "title": "Kennel Sanitation Alert",
        "body": "Kennel K-104 requires daily sanitization. Please complete the cleaning shift and update the logs.",
        "notification_type": "shelter",
        "action_url": "/dashboard/shelter/kennels",
    },
]

SUCCESS_STORIES_DATA = [
    {
        "title": "Bella's Journey: From Rescue to her Forever Home",
        "summary": "Bella was found injured in a rain gutter. Today, she is running free in a large backyard with her loving new family.",
        "body": "Bella was rescued during a heavy storm in early 2026. She was malnourished, terrified, and had a minor leg fracture. Thanks to the quick response of the rescue team and the veterinary care she received in isolation, she made a full recovery. After a thorough vetting process, she was adopted by the Sharma family and now spends her days playing fetch.",
        "status": ContentStatus.PUBLISHED,
        "published_at": datetime.now(UTC),
    },
    {
        "title": "Rex: The Shelter Champion finding a Purpose",
        "summary": "A long-time resident of Kennel Section B, Rex found his perfect partner in an experienced foster caregiver.",
        "body": "Rex came to us with severe trust issues, making him a difficult candidate for direct adoption. He spent several months in the general shelter section under behavioral enrichment. With the patient care of our shelter team and dedicated volunteer training, he began to thrive. He has recently transitioned to foster-to-adopt, proving that every dog deserves time, patience, and love.",
        "status": ContentStatus.PUBLISHED,
        "published_at": datetime.now(UTC),
    },
]

async def seed_db(label: str, database_url: str) -> None:
    if not database_url:
        print(f"SKIP [{label}]: No database URL configured.")
        return

    print(f"SEED [{label}]: Seeding demo data...")
    engine = create_async_engine(
        database_url, echo=False, connect_args={"statement_cache_size": 0}
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        # Fetch all users
        users = (await session.execute(select(User))).scalars().all()
        if not users:
            print(f"  [SKIP] No users found in database to assign notifications to.")
            await engine.dispose()
            return

        # Seed notifications for all active users
        notification_count = 0
        for user in users:
            # Check if notifications already exist for this user
            existing = (
                await session.execute(
                    select(Notification).where(Notification.user_id == user.id)
                )
            ).scalars().first()

            if existing is None:
                for nd in NOTIFICATIONS_DATA:
                    notif = Notification(
                        user_id=user.id,
                        title=nd["title"],
                        body=nd["body"],
                        notification_type=nd["notification_type"],
                        action_url=nd.get("action_url"),
                        is_read=False,
                        is_broadcast=False,
                    )
                    session.add(notif)
                    notification_count += 1

        print(f"  [OK] Added {notification_count} notifications across users.")

        # Seed success stories
        story_count = 0
        for sd in SUCCESS_STORIES_DATA:
            existing = (
                await session.execute(
                    select(SuccessStory).where(SuccessStory.title == sd["title"])
                )
            ).scalars().first()

            if existing is None:
                story = SuccessStory(
                    title=sd["title"],
                    summary=sd["summary"],
                    body=sd["body"],
                    status=sd["status"],
                    published_at=sd["published_at"],
                )
                session.add(story)
                story_count += 1

        print(f"  [OK] Added {story_count} success stories.")

        await session.commit()
        print(f"DONE [{label}]: Demo data seeded successfully.\n")

    await engine.dispose()

async def main() -> None:
    settings = get_settings()
    await seed_db("Backend DB", settings.database_url)
    await seed_db("Frontend DB", settings.database_url_frontend)

if __name__ == "__main__":
    asyncio.run(main())
