"""Seed script for volunteer module data and standard operational users.

Ensures that:
1. All standard operational users (super.admin, volunteer.coordinator, volunteer, etc.) exist,
   are verified (is_verified=True), and have their proper roles assigned.
2. 10+ volunteer applications, profiles, shifts, and attendance records exist with valid data.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add project root and src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from pawguard.core.config import get_settings
from pawguard.core.security import hash_password
from pawguard.modules.auth.models import Role, User, UserRole
from pawguard.modules.volunteer.models import (
    ApplicationStatus,
    AttendanceStatus,
    ShiftAttendance,
    VolunteerApplication,
    VolunteerProfile,
    VolunteerShift,
    VolunteerStatus,
)

OPERATIONAL_ACCOUNTS = [
    ("super.admin@pawguard.com", "Super Admin", "super_admin"),
    ("admin@pawguard.com", "Admin User", "super_admin"),
    ("volunteer.coordinator@pawguard.com", "Volunteer Coordinator", "volunteer_coordinator"),
    ("volunteer@pawguard.com", "Test Volunteer", "volunteer"),
    ("nanda.kishorer@example.com", "Nanda Kishore", "volunteer"),
    ("shelter.manager@pawguard.com", "Shelter Manager", "shelter_manager"),
    ("rescue.coordinator@pawguard.com", "Rescue Coordinator", "rescue_coordinator"),
    ("rescue.agent@pawguard.com", "Rescue Agent", "rescue_agent"),
    ("rescue.admin@pawguard.com", "Rescue Admin", "rescue_centre_admin"),
    ("vet@pawguard.com", "Staff Veterinarian", "veterinarian"),
    ("adoption.coordinator@pawguard.com", "Adoption Coordinator", "adoption_coordinator"),
    ("foster.coordinator@pawguard.com", "Foster Coordinator", "foster_coordinator"),
    ("foster.family@pawguard.com", "Foster Family", "foster_family"),
    ("donor@pawguard.com", "Test Donor", "donor"),
    ("public.user@pawguard.com", "Public User", "general_public"),
]

DEMO_VOLUNTEERS = [
    (
        "Aarav Sharma",
        "aarav.volunteer@pawguard.com",
        "Dog Walking, Basic Training",
        "Weekends",
        "Active Dog Walker",
    ),
    (
        "Priya Patel",
        "priya.volunteer@pawguard.com",
        "Grooming, Bathing, Transport",
        "Weekday Evenings",
        "Experienced Shelter Helper",
    ),
    (
        "Rohan Verma",
        "rohan.volunteer@pawguard.com",
        "Photography, Social Media, Events",
        "Flexible",
        "Can assist with adoption drives",
    ),
    (
        "Ananya Reddy",
        "ananya.volunteer@pawguard.com",
        "Medical Support, Puppy Care",
        "Saturdays",
        "Vet student volunteer",
    ),
    (
        "Vikram Rao",
        "vikram.volunteer@pawguard.com",
        "Transport, Rescue Assistance",
        "On Call",
        "Has large vehicle for dog transport",
    ),
    (
        "Sneha Kulkarni",
        "sneha.volunteer@pawguard.com",
        "Feeding, Kennel Cleaning",
        "Mornings",
        "Reliable daily helper",
    ),
]

DEMO_SHIFTS = [
    ("Morning Kennel Cleaning & Feeding", "dog_walker", 0, 8, 11, 6, "Sector 4 Main Shelter Yard"),
    ("Afternoon Dog Walking & Enrichment", "dog_walker", 1, 14, 17, 8, "Jubilee Hills Rescue Park"),
    (
        "Evening Medical Assistance & Grooming",
        "medical_assistant",
        2,
        16,
        19,
        4,
        "PawGuard Central Clinic",
    ),
    (
        "Weekend Community Adoption Drive",
        "event_staff",
        3,
        10,
        15,
        10,
        "Inorbit Mall Adoption Pavilion",
    ),
    ("Emergency Rescue Standby Shift", "transport", 4, 18, 22, 4, "Hyderabad City Dispatch Center"),
    ("Puppy Socialization & Training", "trainer", 5, 9, 12, 5, "Puppy Nursery Ward A"),
]


async def seed_volunteer_data(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    pw_hash = hash_password("PawGuard@2026")

    # 1. Seed / verify operational accounts
    roles_cache: dict[str, Role] = {}
    for role_name in [
        "super_admin",
        "volunteer_coordinator",
        "volunteer",
        "shelter_manager",
        "rescue_coordinator",
        "rescue_agent",
        "rescue_centre_admin",
        "veterinarian",
        "adoption_coordinator",
        "foster_coordinator",
        "foster_family",
        "donor",
        "general_public",
    ]:
        r = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
        if r:
            roles_cache[role_name] = r

    seeded_users: dict[str, User] = {}
    for email, full_name, primary_role in OPERATIONAL_ACCOUNTS:
        u = (
            await session.execute(
                select(User).options(selectinload(User.roles)).where(User.email == email)
            )
        ).scalar_one_or_none()
        if u is None:
            u = User(
                email=email,
                full_name=full_name,
                hashed_password=pw_hash,
                is_active=True,
                is_verified=True,
                email_verified_at=now,
                phone="+919876543210",
            )
            session.add(u)
            await session.flush()
            print(f"  [USER] Created {email}")
        else:
            u.is_verified = True
            u.is_active = True
            u.hashed_password = pw_hash

        # Grant role if missing
        role_obj = roles_cache.get(primary_role)
        if role_obj:
            existing_ur = (
                await session.execute(
                    select(UserRole).where(
                        UserRole.user_id == u.id, UserRole.role_id == role_obj.id
                    )
                )
            ).scalar_one_or_none()
            if existing_ur is None:
                session.add(UserRole(user_id=u.id, role_id=role_obj.id))
        seeded_users[email] = u

    # Also grant volunteer role to volunteer coordinator and nanda
    vol_role = roles_cache.get("volunteer")
    if vol_role:
        for em in [
            "volunteer.coordinator@pawguard.com",
            "nanda.kishorer@example.com",
            "super.admin@pawguard.com",
        ]:
            user_obj = seeded_users.get(em)
            if user_obj:
                existing_ur = (
                    await session.execute(
                        select(UserRole).where(
                            UserRole.user_id == user_obj.id, UserRole.role_id == vol_role.id
                        )
                    )
                ).scalar_one_or_none()
                if existing_ur is None:
                    session.add(UserRole(user_id=user_obj.id, role_id=vol_role.id))

    await session.flush()

    # 2. Seed Volunteer Profiles for demo volunteers
    created_profiles: list[VolunteerProfile] = []
    for full_name, email, skills, avail, notes in DEMO_VOLUNTEERS:
        u = (
            await session.execute(
                select(User).options(selectinload(User.roles)).where(User.email == email)
            )
        ).scalar_one_or_none()
        if u is None:
            u = User(
                email=email,
                full_name=full_name,
                hashed_password=pw_hash,
                is_active=True,
                is_verified=True,
                email_verified_at=now,
                phone="+919876543210",
            )
            session.add(u)
            await session.flush()
            if vol_role:
                session.add(UserRole(user_id=u.id, role_id=vol_role.id))

        # Check existing application
        app = (
            await session.execute(
                select(VolunteerApplication).where(VolunteerApplication.user_id == u.id)
            )
        ).scalar_one_or_none()
        if app is None:
            app = VolunteerApplication(
                user_id=u.id,
                status=ApplicationStatus.APPROVED,
                emergency_contact_name="Emergency Contact",
                emergency_contact_phone="+919876543211",
                applied_role="Dog Walker / Shelter Helper",
                skills=skills,
                availability=avail,
                notes=notes,
                animal_handling_experience="Over 2 years of handling stray and shelter animals.",
                medical_conditions="None",
                reviewed_by=seeded_users.get("volunteer.coordinator@pawguard.com", u).id,
                reviewed_at=now,
            )
            session.add(app)
            await session.flush()

        # Check existing profile
        prof = (
            await session.execute(select(VolunteerProfile).where(VolunteerProfile.user_id == u.id))
        ).scalar_one_or_none()
        if prof is None:
            prof = VolunteerProfile(
                user_id=u.id,
                application_id=app.id,
                status=VolunteerStatus.ACTIVE,
                emergency_contact_name="Emergency Contact",
                emergency_contact_phone="+919876543211",
                applied_role="Dog Walker / Shelter Helper",
                skills=skills,
                availability=avail,
                notes=notes,
                animal_handling_experience="Over 2 years of handling stray and shelter animals.",
                medical_conditions="None",
                background_check_completed=True,
                background_check_notes="Clear, verified on onboarding.",
            )
            session.add(prof)
            await session.flush()
        created_profiles.append(prof)

    # Also create volunteer profile for volunteer@pawguard.com and nanda.kishorer@example.com
    for em in [
        "volunteer@pawguard.com",
        "nanda.kishorer@example.com",
        "volunteer.coordinator@pawguard.com",
    ]:
        u = seeded_users.get(em)
        if u:
            app = (
                await session.execute(
                    select(VolunteerApplication).where(VolunteerApplication.user_id == u.id)
                )
            ).scalar_one_or_none()
            if app is None:
                app = VolunteerApplication(
                    user_id=u.id,
                    status=ApplicationStatus.APPROVED,
                    emergency_contact_name="Emergency Contact",
                    emergency_contact_phone="+919876543211",
                    applied_role="General Volunteer",
                    skills="Dog Walking, Grooming, Admin",
                    availability="Weekends and Evenings",
                    notes="Verified operational tester.",
                    reviewed_at=now,
                )
                session.add(app)
                await session.flush()
            prof = (
                await session.execute(
                    select(VolunteerProfile).where(VolunteerProfile.user_id == u.id)
                )
            ).scalar_one_or_none()
            if prof is None:
                prof = VolunteerProfile(
                    user_id=u.id,
                    application_id=app.id,
                    status=VolunteerStatus.ACTIVE,
                    emergency_contact_name="Emergency Contact",
                    emergency_contact_phone="+919876543211",
                    applied_role="General Volunteer",
                    skills="Dog Walking, Grooming, Admin",
                    availability="Weekends and Evenings",
                    notes="Verified operational tester.",
                    background_check_completed=True,
                    background_check_notes="Clear verified.",
                )
                session.add(prof)
                await session.flush()
            created_profiles.append(prof)

    # 3. Seed Volunteer Shifts
    created_shifts: list[VolunteerShift] = []
    for _title, role_name, days_ahead, start_h, end_h, cap, loc in DEMO_SHIFTS:
        shift_date = (now + timedelta(days=days_ahead)).date()
        start_dt = datetime(
            shift_date.year, shift_date.month, shift_date.day, start_h, 0, tzinfo=UTC
        )
        end_dt = datetime(shift_date.year, shift_date.month, shift_date.day, end_h, 0, tzinfo=UTC)

        existing_shift = (
            await session.execute(
                select(VolunteerShift).where(
                    VolunteerShift.role_name == role_name, VolunteerShift.location_name == loc
                )
            )
        ).scalar_one_or_none()
        if existing_shift is None:
            shift = VolunteerShift(
                role_name=role_name,
                start_at=start_dt,
                end_at=end_dt,
                capacity=cap,
                location_name=loc,
                latitude=17.4482,
                longitude=78.3741,
                allowed_radius_meters=1000,
            )
            session.add(shift)
            await session.flush()
            created_shifts.append(shift)
        else:
            created_shifts.append(existing_shift)

    # 4. Seed Shift Attendance
    if created_shifts and created_profiles:
        for idx, shift in enumerate(created_shifts[:3]):
            prof = created_profiles[idx % len(created_profiles)]
            existing_att = (
                await session.execute(
                    select(ShiftAttendance).where(
                        ShiftAttendance.shift_id == shift.id,
                        ShiftAttendance.volunteer_id == prof.id,
                    )
                )
            ).scalar_one_or_none()
            if existing_att is None:
                att = ShiftAttendance(
                    shift_id=shift.id,
                    volunteer_id=prof.id,
                    status=AttendanceStatus.CHECKED_OUT,
                    check_in_at=shift.start_at,
                    check_out_at=shift.end_at,
                    hours_logged=3.0,
                    check_in_lat=17.4482,
                    check_in_lng=78.3741,
                    check_out_lat=17.4482,
                    check_out_lng=78.3741,
                )
                session.add(att)

    await session.commit()
    print(
        "  [SUCCESS] Seeded operational users, volunteer profiles, shifts, and attendance records."
    )


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url, echo=False, connect_args={"statement_cache_size": 0}
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        await seed_volunteer_data(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
