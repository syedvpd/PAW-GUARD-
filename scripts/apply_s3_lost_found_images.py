"""Update all Lost and Found reports with real S3 presigned image URLs.

Lists the files in the 'adoption images/' prefix of the pawguard-media
Supabase S3 bucket (or uses predefined presigned URLs) and stores
distinct photo URLs on every LostReport and FoundReport row.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth import models as auth_models  # noqa: F401
from pawguard.modules.companion_pet import models as companion_pet_models  # noqa: F401
from pawguard.modules.dog import models as dog_models  # noqa: F401
from pawguard.modules.foster import models as foster_models  # noqa: F401
from pawguard.modules.rescue import models as rescue_models  # noqa: F401
from pawguard.modules.shelter import models as shelter_models  # noqa: F401
from pawguard.modules.lost_found.models import FoundReport, LostReport

PREDEFINED_URLS = [
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-aryan-prajapati-843541-32687834.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=32f5333af702d6d0854a7ac58b0800c803cceed64dc5410644b2a31233343c3e",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-chithrakadha-12766881.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=6bdd66ddb577938da8183654528e574d07d428385d4d0de7fc0f9dd786452a59",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-cx-lee-2159373144-36111125.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=c16a8576b4d3555113d639dc9a73cd48f99453a21c226caae805ccc81d281f85",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-kyoz-26509909.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=e01a7849da1bf11e1f95d5fced2bd1b88f55774ecbedf5ed1f23c19b24ff88ff",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-kyoz-27732479.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=c17ccd9d0996ea468bfa966465abcc95fb9e9e267d4ad6787dd1ab47fc487775",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-lachlan-ross-6510371.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=6e4b110d3ac32b1df08336672efdd8ec434ec206294b6a016d371e71ba3b32cb",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-miyatavictor-16615010.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=c0cdc3b3369ffc3fe14470fa6fcc6f46ab1236e5c52b9e144dc21411a464b54e",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-sudhirsangwan-34793867.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=6d417b105f6cc3f16db526184ddb4bdc89b58a0e1b9587af471969ec5780ff66",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-tima-miroshnichenko-6234624.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=b539ebc231949114929705beada02a25bcad49fe1b72eb66ceb89b278a03ccba",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-tina-reyes-666324518-36378479.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=555cf2afc1a364620e170959da7624b90bf6e95d390dc07c6d59fccf5d2f3764",
    "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/pexels-vivian-nguyen-42372541-31402709.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260819%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260819T042846Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=4a8db5c09109fc02301df998e3cb456f79e0e7603e3e59d2619895f6e906060f",
]


async def update_reports() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    for attempt in range(1, 11):
        try:
            async with session_factory() as session:
                lost_reports = (await session.execute(select(LostReport))).scalars().all()
                found_reports = (await session.execute(select(FoundReport))).scalars().all()

                print(f"Updating {len(lost_reports)} Lost Reports...")
                for idx, report in enumerate(lost_reports):
                    report.photo_url = PREDEFINED_URLS[idx % len(PREDEFINED_URLS)]

                print(f"Updating {len(found_reports)} Found Reports...")
                for idx, report in enumerate(found_reports):
                    report.photo_url = PREDEFINED_URLS[(idx + 4) % len(PREDEFINED_URLS)]

                await session.commit()
                print(
                    f"SUCCESS: Updated {len(lost_reports)} Lost Reports and {len(found_reports)} Found Reports with S3 photo URLs."
                )
                break
        except Exception as exc:
            print(f"[Attempt {attempt}/10] Connection error: {exc}. Retrying in 3s...")
            await asyncio.sleep(3)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(update_reports())
