"""Script to seed roles, permissions, 15 standard test accounts, verify zero business data,
and test S3 bucket connection on the new Supabase instance.
"""

import asyncio
import sys
from pathlib import Path

# Add project root and src to python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

import boto3
from botocore.client import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

# Import all module models so they register on Base.metadata
from pawguard.modules.auth import models as auth_models  # noqa: F401
from pawguard.modules.rescue import models as rescue_models  # noqa: F401
from pawguard.modules.dog import models as dog_models  # noqa: F401
from pawguard.modules.adoption import models as adoption_models  # noqa: F401
from pawguard.modules.volunteer import models as volunteer_models  # noqa: F401
from pawguard.modules.foster import models as foster_models  # noqa: F401
from pawguard.modules.donation import models as donation_models  # noqa: F401
from pawguard.modules.lost_found import models as lost_found_models  # noqa: F401
from pawguard.modules.medical import models as medical_models  # noqa: F401
from pawguard.modules.shelter import models as shelter_models  # noqa: F401
from pawguard.modules.inventory import models as inventory_models  # noqa: F401
from pawguard.modules.fleet import models as fleet_models  # noqa: F401
from pawguard.modules.grievance import models as grievance_models  # noqa: F401
from pawguard.modules.notifications import models as notification_models  # noqa: F401
from pawguard.modules.portal import models as portal_models  # noqa: F401
from pawguard.modules.finance import models as finance_models  # noqa: F401
from pawguard.modules.storage import models as storage_models  # noqa: F401
from pawguard.modules.settings import models as settings_models  # noqa: F401
from pawguard.modules.companion_pet import models as companion_pet_models  # noqa: F401
from pawguard.modules.outbox import models as outbox_models  # noqa: F401

from pawguard.core.security import hash_password, verify_password
from pawguard.modules.auth.models import Permission, Role, RolePermission, User
from scripts.seed_roles_and_permissions import (
    STANDARD_OPERATIONAL_ACCOUNTS,
    reconcile_roles,
    reconcile_standard_accounts,
)

SUPABASE_DB_URL = "postgresql+asyncpg://postgres.ggzguyqptcedoudfkiev:pawguardstaging%402026@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"

S3_ENDPOINT = "https://ggzguyqptcedoudfkiev.storage.supabase.co/storage/v1/s3"
S3_REGION = "ap-southeast-1"
S3_ACCESS_KEY = "74446ec197d59a56006a69807d86363d"
S3_SECRET_KEY = "e6c3fcb2a5dcf11cbf397ef3f74981e39147e2a4b280e078ae69f48ed6b37d47"
S3_BUCKET = "pawguard-media"


async def setup_database() -> dict[str, int]:
    print("\n--- 1. Connecting to New Supabase Database ---")
    engine = create_async_engine(
        SUPABASE_DB_URL,
        echo=False,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        print("\n--- 2. Reconciling Roles & Granular Permissions ---")
        created_roles, granted_perms = await reconcile_roles(session)
        await session.commit()
        print(
            f"Role/Permission Reconciliation: {created_roles} roles created, {granted_perms} permissions linked."
        )

        print("\n--- 3. Seeding 15 Standard Operational Test Accounts ---")
        acc_result = await reconcile_standard_accounts(session, verbose=True)
        await session.commit()
        print(
            f"Accounts Seeded/Synced: {acc_result['count']} accounts configured with 'PawGuard@2026'."
        )

        print("\n--- 4. Verifying Zero Business Data ---")
        business_tables = [
            "dog_profiles",
            "rescue_requests",
            "rescue_dispatches",
            "shelter_facilities",
            "kennels",
            "adoption_applications",
            "foster_placements",
            "donations",
            "clinical_exams",
            "medical_treatments",
            "vaccination_records",
            "prescriptions",
            "inventory_items",
            "requisition_orders",
            "financial_transactions",
            "grievance_tickets",
            "notifications",
        ]
        table_counts = {}
        for tbl in business_tables:
            res = await session.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            cnt = res.scalar() or 0
            table_counts[tbl] = cnt
            print(f"  - {tbl}: {cnt} rows")

        print("\n--- 5. Validating All 15 Test User Credentials & Roles ---")
        users = (
            (await session.execute(select(User).options(selectinload(User.roles)))).scalars().all()
        )
        for u in sorted(users, key=lambda x: x.email):
            role_names = [r.name for r in u.roles]
            pw_ok = verify_password("PawGuard@2026", u.hashed_password)
            print(
                f"  - [{u.email}] Active={u.is_active} Verified={u.is_verified} Roles={role_names} PasswordOK={pw_ok}"
            )

    await engine.dispose()
    return table_counts


def setup_s3_storage() -> bool:
    print("\n--- 6. Verifying / Initializing Supabase S3 Storage ---")
    s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

    try:
        response = s3_client.list_buckets()
        existing_buckets = [b["Name"] for b in response.get("Buckets", [])]
        print(f"Existing S3 Buckets: {existing_buckets}")

        if S3_BUCKET not in existing_buckets:
            print(f"Creating bucket '{S3_BUCKET}'...")
            s3_client.create_bucket(Bucket=S3_BUCKET)
            print(f"Bucket '{S3_BUCKET}' created successfully.")
        else:
            print(f"Bucket '{S3_BUCKET}' already exists.")

        # Test object write/read/delete
        test_key = "healthcheck/probe.txt"
        s3_client.put_object(Bucket=S3_BUCKET, Key=test_key, Body=b"PawGuard storage verified.")
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=test_key)
        body = obj["Body"].read().decode("utf-8")
        s3_client.delete_object(Bucket=S3_BUCKET, Key=test_key)
        print(f"S3 Read/Write/Delete probe successful: '{body}'")
        return True
    except Exception as e:
        print(f"Storage setup exception: {e}")
        return False


async def main() -> None:
    await setup_database()
    setup_s3_storage()
    print("\n=== SETUP AND VERIFICATION COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
