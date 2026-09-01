"""Seed companion pets and mobile pet appointments into Supabase.

Usage:
    .venv\\Scripts\\python.exe scripts/seed_pet_appointments.py
"""

import asyncio
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth.models import Role, User, UserRole
from pawguard.modules.companion_pet.models import (
    AppointmentStatus,
    CompanionPet,
    PetAppointment,
    VetClinic,
)

REASONS = [
    "Annual Preventive Health Checkup & Rabies Booster",
    "Post-Operative Wound Inspection & Suture Removal",
    "Skin Allergy Diagnostics & Medicated Wash",
    "Dental Tartar Scaling & Oral Examination",
    "Orthopedic Joint Assessment & Mobility Check",
    "Ear Infection Cleaning & Antibiotic Prescription",
    "Microchip Implantation & Registration",
    "Puppy Vaccination Series Dose 2",
    "Senior Canine Arthritis Management",
    "Gastrointestinal Ultrasound Screening",
]

PET_SPECS = [
    ("Simba", "Golden Retriever", "Golden", "male"),
    ("Maximus", "German Shepherd", "Black & Tan", "male"),
    ("Coco", "Labrador Retriever", "Chocolate Brown", "female"),
    ("Whiskey", "Indie Stray Mix", "Fawn", "male"),
    ("Bruno", "Rottweiler", "Black & Mahogany", "male"),
    ("Daisy", "Beagle", "Tri-Color", "female"),
    ("Rocky", "Pug", "Fawn", "male"),
    ("Stella", "Doberman Pinscher", "Black & Rust", "female"),
    ("Milo", "Indie Pariah", "White & Brown", "male"),
    ("Zoe", "Shih Tzu", "White & Gold", "female"),
]


async def main() -> None:
    settings = get_settings()
    print("=========================================================")
    print(" Populating Companion Pets & Mobile Appointments")
    print("=========================================================")

    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        users = (await session.execute(select(User).limit(30))).scalars().all()
        clinics = (
            (await session.execute(select(VetClinic).where(VetClinic.is_active.is_(True))))
            .scalars()
            .all()
        )
        vets = (
            (
                await session.execute(
                    select(User)
                    .join(UserRole, UserRole.user_id == User.id)
                    .join(Role, Role.id == UserRole.role_id)
                    .where(Role.name == "veterinarian")
                )
            )
            .scalars()
            .all()
        )

        if not clinics:
            print("  ERROR: No active vet clinics found. Run seed_veterinary_partners.py first.")
            return

        # Seed companion pets
        pets: list[CompanionPet] = []
        for i, (name, breed, color, sex) in enumerate(PET_SPECS, 1):
            owner = users[(i - 1) % len(users)]
            pet = (
                (
                    await session.execute(
                        select(CompanionPet).where(
                            CompanionPet.name == name,
                            CompanionPet.owner_id == owner.id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not pet:
                pet = CompanionPet(
                    id=uuid.uuid4(),
                    owner_id=owner.id,
                    name=name,
                    species="dog",
                    breed=breed,
                    sex=sex,
                    birth_date=datetime.now(UTC) - timedelta(days=random.randint(300, 1500)),
                    color=color,
                    microchip_id=f"98514100{i:04d}",
                    emergency_notes="Fully vaccinated. No known drug allergies.",
                    is_scan_enabled=True,
                )
                session.add(pet)
                await session.flush()
            pets.append(pet)

        # Seed appointments (spread start times to avoid exclusion constraint conflicts)
        appts_created = 0
        base_time = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

        for i in range(1, 26):
            pet = pets[(i - 1) % len(pets)]
            clinic = clinics[(i - 1) % len(clinics)]
            vet = vets[(i - 1) % len(vets)] if vets else None

            # Non-overlapping: one slot per clinic per 1-hour window offset by index
            day_offset = (i - 1) // 8
            hour_offset = ((i - 1) % 8) * 1  # 1-hour slots
            start_time = base_time + timedelta(days=day_offset - 5, hours=9 + hour_offset)
            end_time = start_time + timedelta(minutes=45)

            # Check for conflict before inserting
            conflict = (
                (
                    await session.execute(
                        select(PetAppointment).where(
                            PetAppointment.clinic_id == clinic.id,
                            PetAppointment.starts_at == start_time,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if conflict:
                continue

            session.add(
                PetAppointment(
                    id=uuid.uuid4(),
                    pet_id=pet.id,
                    owner_id=pet.owner_id,
                    clinic_id=clinic.id,
                    vet_id=vet.id if vet else None,
                    starts_at=start_time,
                    ends_at=end_time,
                    status=random.choice(
                        [
                            AppointmentStatus.CONFIRMED,
                            AppointmentStatus.REQUESTED,
                            AppointmentStatus.COMPLETED,
                        ]
                    ),
                    reason=random.choice(REASONS),
                    notes="Booked via PawGuard Mobile Client App.",
                )
            )
            appts_created += 1

        await session.commit()
        print(f"  Companion pets seeded  : {len(pets)}")
        print(f"  Appointments created   : {appts_created}")
        print("  SUCCESS: Mobile appointments live in Supabase!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
