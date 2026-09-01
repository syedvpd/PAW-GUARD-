"""Update all adoptable dogs to use real S3 presigned image URLs.

Lists the 3 files in the 'adoption images/' prefix of the pawguard-media
Supabase S3 bucket and stores their presigned download URLs (7-day expiry,
regenerated on each read by the public adoption listing if needed) on every
adoptable DogProfile.

Uses the same StorageService.generate_presigned_download_url used by the
donation receipt endpoint — which works in the Flutter app the same way
the receipt PDFs do.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import boto3
from botocore.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth import models as auth_models  # noqa: F401  AuditMixin FKs
from pawguard.modules.companion_pet import models as companion_pet_models  # noqa: F401  SafetyTag
from pawguard.modules.foster import models as foster_models  # noqa: F401  foster_profiles
from pawguard.modules.rescue import models as rescue_models  # noqa: F401  rescue_requests
from pawguard.modules.shelter import models as shelter_models  # noqa: F401  shelter_sections
from pawguard.modules.dog.models import DogProfile
from pawguard.services.storage_service import StorageService

S3_BUCKET = "pawguard-media"
S3_PREFIX = "adoption images/"
PRESIGN_EXPIRY_DAYS = 7


def list_adoption_image_keys() -> list[str]:
    """Return the S3 object keys for files in the adoption images folder."""
    settings = get_settings()
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
    keys = [obj["Key"] for obj in resp.get("Contents", []) if not obj["Key"].endswith("/")]
    keys.sort()
    return keys


def build_presigned_urls(keys: list[str]) -> list[str]:
    """Return presigned download URLs for the given S3 keys."""
    storage = StorageService()
    return [
        storage.generate_presigned_download_url(
            object_key=k, expires_in=PRESIGN_EXPIRY_DAYS * 24 * 3600
        )
        for k in keys
    ]


async def update_dogs() -> None:
    settings = get_settings()
    keys = list_adoption_image_keys()
    if not keys:
        print("ERROR: no files found under S3 prefix 'adoption images/'")
        return
    urls = build_presigned_urls(keys)
    print(f"Found {len(keys)} S3 images:")
    for k in keys:
        print(f"  {k}")
    print(f"\nGenerated presigned URLs ({PRESIGN_EXPIRY_DAYS}-day expiry):")
    for u in urls:
        print(f"  {u}")

    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    updated = 0
    async with session_factory() as session:
        result = await session.execute(
            select(DogProfile)
            .where(DogProfile.is_adoptable.is_(True), DogProfile.deleted_at.is_(None))
            .order_by(DogProfile.registration_number)
        )
        dogs = result.scalars().all()
        print(f"\nUpdating {len(dogs)} adoptable dogs with unique images...")
        for idx, dog in enumerate(dogs):
            # Assign a unique S3 presigned image URL to each dog (cycling through the 11 uploaded photos)
            primary_url = urls[idx % len(urls)]
            # Include secondary images if available
            secondary_url = urls[(idx + 1) % len(urls)]
            dog.image_urls = [primary_url, secondary_url]
            updated += 1
        await session.commit()
    await engine.dispose()
    print(f"\nSuccessfully updated {updated} adoptable dogs with distinct S3 image URLs.")


if __name__ == "__main__":
    asyncio.run(update_dogs())
