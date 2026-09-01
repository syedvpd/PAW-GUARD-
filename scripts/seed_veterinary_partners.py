"""Seed VeterinaryPartner records for the Public Web Portal.

Usage:
    .venv\\Scripts\\python.exe scripts/seed_veterinary_partners.py
"""

import asyncio
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.portal.models import VeterinaryPartner

CLINICS = [
    (
        "Max Vets Hospital & 24/7 Trauma Care",
        "E-Block, Greater Kailash 1, New Delhi, Delhi 110048",
        "+91 11 4173 0400",
        "maxvets.delhi@pawguard.org",
        "Emergency Surgeries, Advanced ICU, Digital X-Ray, Blood Bank, 24/7 Trauma Care",
        28.5528,
        77.2372,
        True,
    ),
    (
        "Apollo Veterinary Medical Centre",
        "100 Feet Rd, HAL 2nd Stage, Indiranagar, Bengaluru, Karnataka 560038",
        "+91 80 2528 1920",
        "apollo.vet.blr@pawguard.org",
        "Orthopedic Surgery, Ultrasound Diagnostics, Pathology Lab, Canine Cardiology",
        12.9784,
        77.6408,
        True,
    ),
    (
        "Bombay SPCA & Animal Hospital",
        "Dr. S. S. Rao Road, Parel, Mumbai, Maharashtra 400012",
        "+91 22 2413 7534",
        "spca.mumbai@pawguard.org",
        "24/7 Emergency Ward, Stray Animal Free Triage, Sterilization Unit, Dental Prophylaxis",
        18.9986,
        72.8423,
        True,
    ),
    (
        "Cure & Care 24-Hour Vet Super-Specialty",
        "Road No. 36, Jubilee Hills, Hyderabad, Telangana 500033",
        "+91 40 2354 8900",
        "curecare.hyd@pawguard.org",
        "Multi-Specialty Surgery, In-House CT Scan, Laparoscopy, Critical Care Unit",
        17.4325,
        78.4071,
        True,
    ),
    (
        "Chennai Pet Wellness Hospital",
        "1st Cross St, Gandhi Nagar, Adyar, Chennai, Tamil Nadu 600020",
        "+91 44 2441 9080",
        "wellness.chennai@pawguard.org",
        "General Medicine, Orthopedics, Endoscopy, Canine Vaccination & Preventive Health",
        13.0067,
        80.2570,
        False,
    ),
    (
        "Crown Vet Emergency Clinic",
        "Arch No. 28, Below Mahalaxmi Bridge, Mumbai, Maharashtra 400011",
        "+91 22 2490 1200",
        "crownvet.mumbai@pawguard.org",
        "Round-the-clock Emergency Diagnostics, Oxygen Therapy, Microchipping, Soft Tissue Surgery",
        18.9827,
        72.8258,
        True,
    ),
    (
        "Cessna Lifeline Veterinary Hospital",
        "HCBS Domlur Layout, Airport Road, Bengaluru, Karnataka 560071",
        "+91 80 4160 0999",
        "cessna.blr@pawguard.org",
        "Intensive Care Unit (ICU), Dialysis, Ophthalmology, Advanced Dermatological Diagnostics",
        12.9610,
        77.6387,
        True,
    ),
    (
        "Pet Point Veterinary Poly-Clinic",
        "Sector 14, Gurugram, Haryana 122001",
        "+91 124 408 5566",
        "petpoint.ncr@pawguard.org",
        "OPD Consultations, Vaccinations, Deworming, Minor Surgeries, Wellness Checkups",
        28.4732,
        77.0422,
        False,
    ),
    (
        "Pune Canine Healthcare & Surgical Hub",
        "North Main Road, Koregaon Park, Pune, Maharashtra 411001",
        "+91 20 2615 4433",
        "caninehub.pune@pawguard.org",
        "Emergency Trauma Center, Canine Physiotherapy, Hydrotherapy, Radiology Suite",
        18.5362,
        73.8940,
        True,
    ),
    (
        "Kolkata Veterinary Care Centre",
        "Salt Lake Sector V, Bidhannagar, Kolkata, West Bengal 700091",
        "+91 33 2357 8899",
        "vetcare.kolkata@pawguard.org",
        "General Health Screenings, Pet Passport Assistance, Vaccinations, General Surgery",
        22.5804,
        88.4378,
        False,
    ),
    (
        "Ahmedabad Companion Animal Clinic",
        "Sindhu Bhavan Marg, Bodakdev, Ahmedabad, Gujarat 380054",
        "+91 79 2685 1122",
        "ahmedabad.vet@pawguard.org",
        "Dental Surgery, Ultrasonic Scaler, In-House Blood Analyzers, Emergency Care",
        23.0456,
        72.5089,
        True,
    ),
    (
        "Jaipur Royal Pet Medical Center",
        "Tonk Road, Bapu Nagar, Jaipur, Rajasthan 302015",
        "+91 141 270 9988",
        "royalpet.jaipur@pawguard.org",
        "Preventive Care, Rabies Eradication Unit, Laser Therapy, Pet Grooming & Spa",
        26.8854,
        75.8073,
        False,
    ),
]


async def main() -> None:
    settings = get_settings()
    print("=========================================================")
    print(" Populating veterinary_partners for Public Portal")
    print("=========================================================")

    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        added = 0
        for name, address, phone, email, services, lat, lng, is_emerg in CLINICS:
            existing = (
                (
                    await session.execute(
                        select(VeterinaryPartner).where(VeterinaryPartner.name == name)
                    )
                )
                .scalars()
                .first()
            )
            if not existing:
                session.add(
                    VeterinaryPartner(
                        id=uuid.uuid4(),
                        name=name,
                        address=address,
                        phone=phone,
                        email=email,
                        services=services,
                        latitude=Decimal(str(lat)),
                        longitude=Decimal(str(lng)),
                        is_emergency=is_emerg,
                        is_active=True,
                    )
                )
                added += 1
        await session.commit()
        print(f"  SUCCESS: {added} VeterinaryPartner records committed!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
