"""Seed veterinarian user accounts and assign them to vet clinics.

Usage:
    .venv\\Scripts\\python.exe scripts/seed_veterinarians.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.core.security import hash_password
from pawguard.modules.auth.models import Role, User, UserRole
from pawguard.modules.companion_pet.models import ClinicMembership, VetClinic

VETS = [
    {"full_name": "Dr. Priya Mehta",     "email": "dr.priya.mehta@pawguard.org",     "phone": "+91 98100 11001", "clinic_name": "Max Vets Hospital & 24/7 Trauma Care",          "specialisation": "Small Animal Internal Medicine"},
    {"full_name": "Dr. Arjun Sharma",    "email": "dr.arjun.sharma@pawguard.org",    "phone": "+91 98100 11002", "clinic_name": "Max Vets Hospital & 24/7 Trauma Care",          "specialisation": "Veterinary Surgery & Orthopaedics"},
    {"full_name": "Dr. Nandita Iyer",    "email": "dr.nandita.iyer@pawguard.org",    "phone": "+91 98100 11003", "clinic_name": "Apollo Veterinary Medical Centre",             "specialisation": "Veterinary Cardiology"},
    {"full_name": "Dr. Rohan Kapoor",    "email": "dr.rohan.kapoor@pawguard.org",    "phone": "+91 98100 11004", "clinic_name": "Bombay SPCA & Animal Hospital",                "specialisation": "Emergency & Critical Care"},
    {"full_name": "Dr. Sunita Rao",      "email": "dr.sunita.rao@pawguard.org",      "phone": "+91 98100 11005", "clinic_name": "Cessna Lifeline Veterinary Hospital",          "specialisation": "Canine Dermatology"},
    {"full_name": "Dr. Vikram Nair",     "email": "dr.vikram.nair@pawguard.org",     "phone": "+91 98100 11006", "clinic_name": "Cessna Lifeline Veterinary Hospital",          "specialisation": "Veterinary Oncology"},
    {"full_name": "Dr. Deepa Pillai",    "email": "dr.deepa.pillai@pawguard.org",    "phone": "+91 98100 11007", "clinic_name": "Cure & Care 24-Hour Vet Super-Specialty",      "specialisation": "Canine Ophthalmology"},
    {"full_name": "Dr. Kiran Joshi",     "email": "dr.kiran.joshi@pawguard.org",     "phone": "+91 98100 11008", "clinic_name": "Chennai Pet Wellness Hospital",                "specialisation": "General Practice & Preventive Medicine"},
    {"full_name": "Dr. Anita Desai",     "email": "dr.anita.desai@pawguard.org",     "phone": "+91 98100 11009", "clinic_name": "Crown Vet Emergency Clinic",                   "specialisation": "Veterinary Anaesthesiology"},
    {"full_name": "Dr. Suresh Bhat",     "email": "dr.suresh.bhat@pawguard.org",     "phone": "+91 98100 11010", "clinic_name": "Pune Canine Healthcare & Surgical Hub",        "specialisation": "Radiology & Diagnostic Imaging"},
    {"full_name": "Dr. Meera Krishnan",  "email": "dr.meera.krishnan@pawguard.org",  "phone": "+91 98100 11011", "clinic_name": "Pune Canine Healthcare & Surgical Hub",        "specialisation": "Canine Neurology"},
    {"full_name": "Dr. Rajesh Gupta",    "email": "dr.rajesh.gupta@pawguard.org",    "phone": "+91 98100 11012", "clinic_name": "Ahmedabad Companion Animal Clinic",            "specialisation": "Canine Dentistry & Oral Surgery"},
    {"full_name": "Dr. Lakshmi Venkat",  "email": "dr.lakshmi.venkat@pawguard.org",  "phone": "+91 98100 11013", "clinic_name": "Kolkata Veterinary Care Centre",               "specialisation": "Reproduction & Neonatology"},
    {"full_name": "Dr. Anil Mathur",     "email": "dr.anil.mathur@pawguard.org",     "phone": "+91 98100 11014", "clinic_name": "Jaipur Royal Pet Medical Center",              "specialisation": "Exotic Animal & Wildlife Medicine"},
    {"full_name": "Dr. Pooja Singh",     "email": "dr.pooja.singh@pawguard.org",     "phone": "+91 98100 11015", "clinic_name": "Pet Point Veterinary Poly-Clinic",             "specialisation": "Animal Physiotherapy & Rehabilitation"},
]

PASSWORD = "PawGuard@2026"


async def main() -> None:
    settings = get_settings()
    print("=========================================================")
    print(" Seeding Veterinarian Accounts & Clinic Memberships")
    print("=========================================================")

    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    hashed_pw = hash_password(PASSWORD)

    async with session_factory() as session:
        vet_role = (await session.execute(select(Role).where(Role.name == "veterinarian"))).scalars().first()
        if not vet_role:
            vet_role = Role(id=uuid.uuid4(), name="veterinarian", description="Licensed Veterinarian")
            session.add(vet_role)
            await session.flush()

        all_clinics = (await session.execute(select(VetClinic))).scalars().all()
        clinic_map = {c.name: c for c in all_clinics}

        users_created = 0
        memberships_created = 0

        for vet in VETS:
            existing = (await session.execute(select(User).where(User.email == vet["email"]))).scalars().first()
            if existing:
                vet_user = existing
            else:
                vet_user = User(
                    id=uuid.uuid4(),
                    email=vet["email"],
                    phone=vet["phone"],
                    full_name=vet["full_name"],
                    hashed_password=hashed_pw,
                    is_active=True,
                    is_verified=True,
                )
                session.add(vet_user)
                await session.flush()
                users_created += 1

            existing_role = (await session.execute(
                select(UserRole).where(UserRole.user_id == vet_user.id, UserRole.role_id == vet_role.id)
            )).scalars().first()
            if not existing_role:
                session.add(UserRole(user_id=vet_user.id, role_id=vet_role.id))

            clinic = clinic_map.get(vet["clinic_name"])
            if clinic:
                existing_mbr = (await session.execute(
                    select(ClinicMembership).where(
                        ClinicMembership.clinic_id == clinic.id,
                        ClinicMembership.user_id == vet_user.id,
                    )
                )).scalars().first()
                if not existing_mbr:
                    session.add(ClinicMembership(
                        id=uuid.uuid4(),
                        clinic_id=clinic.id,
                        user_id=vet_user.id,
                        membership_role="veterinarian",
                        is_active=True,
                    ))
                    memberships_created += 1

        await session.commit()

    await engine.dispose()
    print(f"  Vet accounts created   : {users_created}")
    print(f"  Memberships created    : {memberships_created}")
    print(f"  Password for all vets  : {PASSWORD}")
    print("  SUCCESS: Veterinarians live in Supabase!")


if __name__ == "__main__":
    asyncio.run(main())
