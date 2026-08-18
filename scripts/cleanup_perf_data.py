"""Remove perf*-prefixed load-test pollution from the database.

Run against the target environment:
    python scripts/cleanup_perf_data.py  # uses DATABASE_URL from env

This is a destructive operation — always run against a backup first.
"""

import asyncio
import os
import sys

from sqlalchemy import delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


async def cleanup(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}

    # 1. Fix vet@pawguard.com identity fields overwritten by perf data
    from pawguard.modules.auth.models import User
    result = await session.execute(
        update(User)
        .where(User.email == "vet@pawguard.com")
        .where(or_(User.full_name.like("perf%"), User.phone.like("perf%")))
        .values(full_name="Staff Veterinarian", phone="")
        .returning(User.id)
    )
    counts["users_fixed"] = len(result.all())

    # 2. Delete perf* rescue reports (rescue_requests with perf* reporter data)
    from pawguard.modules.rescue.models import RescueRequest
    result = await session.execute(
        delete(RescueRequest)
        .where(or_(
            RescueRequest.reporter_name.like("perf%"),
            RescueRequest.reporter_phone.like("perf%"),
            RescueRequest.location_address.like("perf%"),
        ))
    )
    counts["rescue_requests_deleted"] = result.rowcount or 0

    # 3. Delete perf* shelters (shelter_facilities with generic names)
    from pawguard.modules.shelter.models import ShelterFacility
    result = await session.execute(
        delete(ShelterFacility)
        .where(ShelterFacility.name.like("perf%"))
    )
    counts["shelters_deleted"] = result.rowcount or 0

    # 4. Delete perf* vaccine protocols (medical treatments with perf* data)
    # These are in medical_treatments or vaccine_protocols tables
    from pawguard.modules.medical.models import MedicalTreatment
    result = await session.execute(
        delete(MedicalTreatment)
        .where(or_(
            MedicalTreatment.treatment_type.like("perf%"),
            MedicalTreatment.notes.like("perf%"),
        ))
    )
    counts["treatments_deleted"] = result.rowcount or 0

    # 5. Delete perf* prescriptions
    from pawguard.modules.medical.models import Prescription
    result = await session.execute(
        delete(Prescription)
        .where(or_(
            Prescription.medication_name.like("perf%"),
            Prescription.notes.like("perf%"),
        ))
    )
    counts["prescriptions_deleted"] = result.rowcount or 0

    await session.commit()
    return counts


async def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set.")
        sys.exit(1)

    # Convert postgres:// to postgresql+asyncpg://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        counts = await cleanup(session)

    print("Cleanup complete:")
    for key, val in counts.items():
        print(f"  {key}: {val}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
