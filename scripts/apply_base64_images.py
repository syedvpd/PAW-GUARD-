"""Download S3 adoption images and store as base64 data URIs in dog_profiles.

This approach guarantees every client can display images regardless of:
- CORS configuration on the S3 bucket
- Field name mismatches (image_urls vs photo_gallery_urls vs imageUrl)
- Presigned URL expiry
- Supabase S3 presigned GET returning 403 in some contexts

Reads each image from S3, converts to a data URI, and stores on
image_urls for all adoptable dogs. The Flutter app will receive
the base64 data directly in the JSON response.
"""

import asyncio
import base64
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import boto3
from botocore.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth import models as auth_models  # noqa: F401
from pawguard.modules.companion_pet import models as companion_pet_models  # noqa: F401
from pawguard.modules.foster import models as foster_models  # noqa: F401
from pawguard.modules.rescue import models as rescue_models  # noqa: F401
from pawguard.modules.shelter import models as shelter_models  # noqa: F401
from pawguard.modules.dog.models import DogProfile

S3_BUCKET = "pawguard-media"
S3_PREFIX = "adoption images/"


def make_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def download_images_as_data_uris() -> list[str]:
    """Download each image from S3 and return as base64 data URIs."""
    s3 = make_s3_client()
    keys = [
        "adoption images/ad1.jfif",
        "adoption images/ad2.webp",
        "adoption images/ad3.webp",
    ]
    data_uris = []
    for key in keys:
        resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
        body: bytes = resp["Body"].read()
        content_type = mimetypes.guess_type(key)[0] or "image/jpeg"
        encoded = base64.b64encode(body).decode("ascii")
        data_uris.append(f"data:{content_type};base64,{encoded}")
        print(f"  {key}: {len(body)} bytes -> data URI ({len(data_uris[-1])} chars)")
    return data_uris


async def apply() -> None:
    settings = get_settings()
    data_uris = download_images_as_data_uris()
    print(f"\nGenerated {len(data_uris)} data URIs")

    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    updated = 0
    async with session_factory() as session:
        for status_filter in ("shelter", "fostered", "rescued", "clinic"):
            result = await session.execute(
                select(DogProfile).where(
                    DogProfile.status == status_filter,
                    DogProfile.is_adoptable.is_(True),
                    DogProfile.deleted_at.is_(None),
                )
            )
            for dog in result.scalars().all():
                dog.image_urls = data_uris
                updated += 1
                print(
                    f"  {dog.name} ({dog.registration_number}): {status_filter} -> {len(data_uris)} data URIs"
                )

        # Also update adopted dogs
        result = await session.execute(
            select(DogProfile).where(
                DogProfile.status == "adopted",
                DogProfile.deleted_at.is_(None),
            )
        )
        for dog in result.scalars().all():
            dog.image_urls = data_uris
            updated += 1
            print(
                f"  {dog.name} ({dog.registration_number}): adopted -> {len(data_uris)} data URIs"
            )

        await session.commit()
    await engine.dispose()
    print(f"\nUpdated {updated} dogs with base64 data URI images.")


if __name__ == "__main__":
    asyncio.run(apply())
