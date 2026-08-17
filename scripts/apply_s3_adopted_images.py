"""Update all ADOPTED dogs to use real S3 presigned image URLs.

Same pattern as apply_s3_adoption_images.py but scoped to dogs with
status='adopted' so any 'adopted dogs' / 'happy tails' section in the
Flutter app has photos for dogs that were previously adopted.

Replaces placeholder URLs (Unsplash etc.) and fills in missing
image_urls for dogs that had none.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth import models as auth_models  # noqa: F401
from pawguard.modules.companion_pet import models as companion_pet_models  # noqa: F401
from pawguard.modules.foster import models as foster_models  # noqa: F401
from pawguard.modules.rescue import models as rescue_models  # noqa: F401
from pawguard.modules.shelter import models as shelter_models  # noqa: F401
from pawguard.modules.dog.models import DogProfile
from pawguard.services.storage_service import StorageService

S3_BUCKET = "pawguard-media"
S3_PREFIX = "adoption images/"
PRESIGN_EXPIRY_DAYS = 7


def build_adoption_image_urls() -> list[str]:
    """Return presigned download URLs for the 3 adoption images in S3."""
    storage = StorageService()
    return [
        storage.generate_presigned_download_url(
            object_key=f"{S3_PREFIX}{name}",
            expires_in=PRESIGN_EXPIRY_DAYS * 24 * 3600,
        )
        for name in ["ad1.jfif", "ad2.webp", "ad3.webp"]
    ]


async def update_adopted_dogs() -> None:
    settings = get_settings()
    urls = build_adoption_image_urls()
    print(f"Generated {len(urls)} presigned URLs ({PRESIGN_EXPIRY_DAYS}-day expiry)")

    engine = create_async_engine(
        settings.database_url, connect_args={"statement_cache_size": 0}
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    updated = 0
    async with session_factory() as session:
        result = await session.execute(
            select(DogProfile)
            .where(
                DogProfile.status == "adopted",
                DogProfile.deleted_at.is_(None),
            )
            .order_by(DogProfile.registration_number)
        )
        dogs = result.scalars().all()
        print(f"\nFound {len(dogs)} adopted dogs:")
        for dog in dogs:
            old = len(dog.image_urls) if dog.image_urls else 0
            dog.image_urls = urls
            print(f"  {dog.name} ({dog.registration_number}): {old} -> {len(urls)} images")
            updated += 1
        await session.commit()
    await engine.dispose()
    print(f"\nUpdated {updated} adopted dogs with S3 presigned image URLs.")


if __name__ == "__main__":
    asyncio.run(update_adopted_dogs())
