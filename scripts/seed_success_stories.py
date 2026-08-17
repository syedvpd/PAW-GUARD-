"""Seed script for published success stories shown on the public portal.

Populates the success_stories table with sample stories linked to seeded
dogs so the public Flutter app's Community > Success Stories tab has
content. Re-running this script is idempotent: existing stories are
matched by title and skipped.

Usage:
    .venv\\Scripts\\python.exe scripts/seed_success_stories.py
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.portal.models import ContentStatus, SuccessStory


def _published_now() -> datetime:
    return datetime.now(UTC)


STORIES = [
    {
        "title": "Bruno's Big Adventure: From Streets to Sofa",
        "summary": (
            "Found limping near Sector 4, Bruno now spends his afternoons "
            "napping on the family sofa and chasing tennis balls in the park."
        ),
        "body": (
            "Bruno was first spotted by a passing auto driver who noticed him "
            "limping near a busy intersection. Our rescue team reached him "
            "within the hour. He had a fractured front leg, severe tick "
            "infestation, and was underweight. After three months of medical "
            "care, rehabilitation, and behavioral training at our shelter, "
            "Bruno was ready for adoption.\n\n"
            "The Sharma family met Bruno on a Saturday open-house day. Their "
            "two children fell in love instantly. Today, Bruno is a fully "
            "recovered, happy family dog who loves weekend trips to Cubbon "
            "Park and is famously afraid of the neighbor's vacuum cleaner."
        ),
        "hero_image_url": "https://images.dog.ceo/breeds/retriever-indian/n02110185_10369.jpg",
        "dog_registration": "DOG-2026-0001",
    },
    {
        "title": "Bella Finds Her Forever Home",
        "summary": (
            "Rescued as a pregnant stray, Bella gave birth to four healthy "
            "puppies and has now been adopted by a loving couple."
        ),
        "body": (
            "Bella was found abandoned near an industrial estate, visibly "
            "pregnant and scared. Our field team brought her to the clinic "
            "where she delivered four healthy puppies within a week. All "
            "five were fostered by our network, with Bella's puppies finding "
            "homes first.\n\n"
            "When Bella was ready for adoption, the Patel family came "
            "forward. They had recently lost their senior Labrador and wanted "
            "a gentle companion. Bella now enjoys long morning walks and has "
            "become the beloved matriarch of the Patel's small farm."
        ),
        "hero_image_url": "https://images.dog.ceo/breeds/labrador/n02099712_4497.jpg",
        "dog_registration": "DOG-2026-0002",
    },
    {
        "title": "Rocky's Second Chance",
        "summary": (
            "Abandoned after a road accident, Rocky learned to trust again "
            "and now serves as a therapy dog at a children's hospital."
        ),
        "body": (
            "Rocky was brought to us with a severe spinal injury after being "
            "hit by a vehicle. Surgery and weeks of physiotherapy followed. "
            "Against all odds, he recovered and was placed with our "
            "experienced foster, Dr. Anita.\n\n"
            "Dr. Anita, a child psychologist, recognized Rocky's calm "
            "temperament and trained him as a therapy dog. Rocky now visits "
            "the pediatric oncology ward every weekend, bringing smiles to "
            "children undergoing treatment."
        ),
        "hero_image_url": "https://images.dog.ceo/breeds/germanshepherd/n02106625_22496.jpg",
        "dog_registration": "DOG-2026-0003",
    },
    {
        "title": "Luna and the Letter",
        "summary": (
            "Eight-month-old Luna was adopted by a family who wrote us the "
            "sweetest thank-you letter. Here's their story."
        ),
        "body": (
            "Luna was one of four puppies born at our shelter to a rescued "
            "mother. From day one, she was the most curious and playful. "
            "When the Iyer family visited looking for a companion for their "
            "son Arjun, Luna picked them.\n\n"
            "Six months later, the Iyers sent us a letter. In neat "
            "handwriting, young Arjun wrote: 'Thank you for giving us Luna. "
            "She sleeps on my bed and I read her stories. She is my best "
            "friend.' That letter is now framed in our shelter lobby."
        ),
        "hero_image_url": "https://images.dog.ceo/breeds/beagle/n02088364_12628.jpg",
        "dog_registration": "DOG-2026-0004",
    },
    {
        "title": "Max the Marathon Runner",
        "summary": (
            "Once a stray who flinched at raised hands, Max now runs 10Ks "
            "with his adopter every weekend."
        ),
        "body": (
            "Max came to us with clear signs of past abuse - he flinched at "
            "any sudden movement and cowered at raised hands. Our "
            "behavioral team worked with him for months, gradually building "
            "his confidence.\n\n"
            "Rohan, a marathon runner, met Max at an adoption drive. He was "
            "drawn to Max's quiet dignity. Today, Max completes 10K runs "
            "alongside Rohan every Sunday morning and has become a local "
            "celebrity in their running club."
        ),
        "hero_image_url": "https://images.dog.ceo/breeds/retriever-golden/n02099601_3787.jpg",
        "dog_registration": "DOG-2026-0005",
    },
    {
        "title": "Daisy's First Christmas",
        "summary": (
            "Six-month-old Daisy experienced her first festive season in a "
            "warm home. Here are the highlights."
        ),
        "body": (
            "Daisy was found as a tiny puppy near a construction site, "
            "terrified of humans. Months of patient socialization at our "
            "shelter transformed her into a confident, affectionate young "
            "dog. The Kapoor family adopted her just in time for the "
            "festive season.\n\n"
            "Her first Christmas included her very first wrapped gift (a "
            "squeaky toy, naturally), her first taste of dog-friendly "
            "festive treats, and her first family photo. She has since "
            "become the official greeter at the Kapoor residence."
        ),
        "hero_image_url": "https://images.dog.ceo/breeds/cavalier-king-charles-spaniel/n02085711_3676.jpg",
        "dog_registration": "DOG-2026-0006",
    },
]


async def seed_success_stories() -> None:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url, connect_args={"statement_cache_size": 0}
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        # Map dog registration numbers to IDs for FK linking.
        dog_ids: dict[str, uuid.UUID] = {}
        for reg in {s["dog_registration"] for s in STORIES}:
            dog = (
                await session.execute(
                    select(DogProfile).where(DogProfile.registration_number == reg)
                )
            ).scalars().first()
            if dog is not None:
                dog_ids[reg] = dog.id

        created = 0
        for story_data in STORIES:
            existing = (
                await session.execute(
                    select(SuccessStory).where(SuccessStory.title == story_data["title"])
                )
            ).scalars().first()
            if existing is not None:
                continue

            story = SuccessStory(
                id=uuid.uuid4(),
                title=story_data["title"],
                summary=story_data["summary"],
                body=story_data["body"],
                hero_image_url=story_data["hero_image_url"],
                dog_id=dog_ids.get(story_data["dog_registration"]),
                status=ContentStatus.PUBLISHED,
                published_at=_published_now(),
            )
            session.add(story)
            created += 1

        await session.commit()
    await engine.dispose()
    print(f"Seed success stories completed ({created} new, {len(STORIES) - created} existing).")


if __name__ == "__main__":
    asyncio.run(seed_success_stories())
