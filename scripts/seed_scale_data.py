import argparse
import asyncio
import os
import random
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Ensure pawguard package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pawguard.core.config import get_settings
from pawguard.core.constants import Environment
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth.models import AuthAuditLog, Role, User, UserRole
from pawguard.modules.dog.models import (
    DogBreedClassification,
    DogGender,
    DogProfile,
    DogStatus,
)
from pawguard.modules.donation.models import (
    Donation,
    DonationStatus,
    DonationType,
)
from pawguard.modules.foster.models import FosterPlacement, FosterProfile, FosterStatus
from pawguard.modules.medical.models import ClinicalExam, VaccinationRecord
from pawguard.modules.notifications.models import Notification, NotificationPreference
from pawguard.modules.shelter.models import FacilityStatus, ShelterFacility
from pawguard.modules.volunteer.models import VolunteerProfile, VolunteerShift, VolunteerStatus

# Preset dummy Argon2 hash for speed during test seeding ("Password123!")
DUMMY_ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$vH8t76B8Q6T/q7a0V0+6+w$O8P0Zf6P+k0Q8r/6K3eZ9G6s5d4c3b2a1"

SCALE_PROFILES: dict[str, dict[str, int]] = {
    "test": {
        "users": 100,
        "shelters": 5,
        "dogs": 30,
        "medical_records": 60,
        "adoptions": 40,
        "fosters": 15,
        "volunteers": 20,
        "donations": 50,
        "notifications": 250,
        "audit_logs": 500,
    },
    "10k": {
        "users": 10_000,
        "shelters": 50,
        "dogs": 2_500,
        "medical_records": 6_000,
        "adoptions": 3_500,
        "fosters": 1_000,
        "volunteers": 1_500,
        "donations": 5_000,
        "notifications": 25_000,
        "audit_logs": 60_000,
    },
    "50k": {
        "users": 50_000,
        "shelters": 150,
        "dogs": 12_000,
        "medical_records": 30_000,
        "adoptions": 18_000,
        "fosters": 5_000,
        "volunteers": 7_500,
        "donations": 25_000,
        "notifications": 125_000,
        "audit_logs": 300_000,
    },
    "100k": {
        "users": 100_000,
        "shelters": 300,
        "dogs": 25_000,
        "medical_records": 65_000,
        "adoptions": 38_000,
        "fosters": 10_000,
        "volunteers": 15_000,
        "donations": 50_000,
        "notifications": 250_000,
        "audit_logs": 650_000,
    },
    "500k": {
        "users": 500_000,
        "shelters": 1_000,
        "dogs": 120_000,
        "medical_records": 320_000,
        "adoptions": 180_000,
        "fosters": 50_000,
        "volunteers": 75_000,
        "donations": 250_000,
        "notifications": 1_250_000,
        "audit_logs": 3_200_000,
    },
    "1m": {
        "users": 1_000_000,
        "shelters": 2_000,
        "dogs": 250_000,
        "medical_records": 650_000,
        "adoptions": 380_000,
        "fosters": 100_000,
        "volunteers": 150_000,
        "donations": 500_000,
        "notifications": 2_500_000,
        "audit_logs": 6_500_000,
    },
}


def assert_production_safety(db_url: str) -> None:
    """Enforce strict production safeguards against accidental scale data pollution."""
    settings = get_settings()
    if settings.environment == Environment.PRODUCTION:
        raise RuntimeError("CRITICAL: Scale data generator cannot run in PRODUCTION environment.")

    forbidden_keywords = ("prod", "production", "live-db", "pawguard.com", "rds.amazonaws.com")
    lower_url = db_url.lower()
    for kw in forbidden_keywords:
        if kw in lower_url and "local" not in lower_url and "test" not in lower_url:
            raise RuntimeError(f"CRITICAL: Database URL contains production keyword '{kw}'. Aborting.")


class ScaleDataGenerator:
    def __init__(
        self,
        db_url: str,
        scale: str,
        seed: int = 12345,
        batch_size: int = 2000,
        dry_run: bool = False,
    ) -> None:
        self.db_url = db_url
        self.scale = scale
        self.seed = seed
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.rng = random.Random(seed)  # noqa: S311  # nosec B311
        self.counts = SCALE_PROFILES.get(scale, SCALE_PROFILES["test"])
        # Fixed epoch anchor to ensure 100% deterministic seed reproducibility
        self.now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

    def random_past_date(self, days_back: int = 730) -> datetime:
        seconds = self.rng.randint(0, days_back * 86400)
        return self.now - timedelta(seconds=seconds)

    def format_progress(self, entity: str, current: int, total: int, start_time: float) -> str:
        pct = (current / total * 100) if total else 100
        elapsed = time.perf_counter() - start_time
        return f"[{entity:18}] {current:8d} / {total:8d} ({pct:5.1f}%) | Elapsed: {elapsed:6.1f}s"

    async def run(self) -> dict[str, Any]:
        assert_production_safety(self.db_url)
        print("\n=======================================================")
        print(f" PawGuard Scale Data Generator — Scale: {self.scale.upper()} (Seed: {self.seed})")
        print(f" Dry Run: {self.dry_run} | Batch Size: {self.batch_size}")
        print("=======================================================")
        for entity, count in self.counts.items():
            print(f"  {entity:22}: {count:,}")
        print("=======================================================\n")

        if self.dry_run:
            print("Dry run completed successfully. Zero database modifications performed.")
            return {"status": "dry_run_success", "estimated_counts": self.counts}

        engine = create_async_engine(
            self.db_url,
            pool_size=10,
            max_overflow=20,
            connect_args={"statement_cache_size": 0},
        )

        start_time = time.perf_counter()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            # 1. Fetch or create roles
            role_map = await self._ensure_roles(session)

            # 2. Generate Shelters
            shelter_ids = await self._generate_shelters(session)

            # 3. Generate Users & Sessions & Roles
            user_ids, vet_ids, foster_user_ids, volunteer_user_ids, donor_user_ids = (
                await self._generate_users(session, role_map)
            )

            # 4. Generate Dogs & Activity
            dog_ids = await self._generate_dogs(session, shelter_ids)

            # 5. Generate Medical Records
            await self._generate_medical(session, dog_ids, vet_ids)

            # 6. Generate Adoption Applications
            await self._generate_adoptions(session, dog_ids, user_ids)

            # 7. Generate Foster Profiles & Placements
            await self._generate_fosters(session, dog_ids, foster_user_ids)

            # 8. Generate Volunteer Shifts & Attendance
            await self._generate_volunteers(session, volunteer_user_ids, shelter_ids)

            # 9. Generate Donations & Sponsorships
            await self._generate_donations(session, donor_user_ids, dog_ids)

            # 10. Generate Notifications & Audit Logs
            await self._generate_telemetry_logs(session, user_ids)

            await session.commit()

        total_elapsed = time.perf_counter() - start_time
        print(f"\nGeneration complete in {total_elapsed:.2f}s!")
        return {"status": "success", "duration_seconds": total_elapsed, "counts": self.counts}

    async def _ensure_roles(self, session: AsyncSession) -> dict[str, uuid.UUID]:
        res = await session.execute(select(Role))
        roles = res.scalars().all()
        role_map = {r.name: r.id for r in roles}
        default_roles = ["PUBLIC_USER", "DONOR", "VOLUNTEER", "FOSTER_PARENT", "VET_STAFF", "RESCUE_STAFF", "SUPER_ADMIN"]
        for r_name in default_roles:
            if r_name not in role_map:
                r_id = uuid.uuid4()
                role_obj = Role(id=r_id, name=r_name, description=f"Role {r_name}", is_system=True)
                session.add(role_obj)
                role_map[r_name] = r_id
        await session.flush()
        return role_map

    async def _generate_shelters(self, session: AsyncSession) -> list[uuid.UUID]:
        target = self.counts["shelters"]
        shelter_ids: list[uuid.UUID] = []
        t0 = time.perf_counter()
        for i in range(target):
            s_id = uuid.uuid4()
            shelter_ids.append(s_id)
            shelter = ShelterFacility(
                id=s_id,
                name=f"Shelter Facility {i+1} (Seed-{self.seed})",
                address=f"{self.rng.randint(100, 999)} Rescue Way, Sector {self.rng.randint(1, 50)}",
                phone=f"+91{self.rng.randint(7000000000, 9999999999)}",
                latitude=round(12.9 + self.rng.uniform(-0.5, 0.5), 6),
                longitude=round(77.5 + self.rng.uniform(-0.5, 0.5), 6),
                total_capacity=self.rng.randint(30, 150),
                status=FacilityStatus.ACTIVE,
                created_at=self.random_past_date(),
            )
            session.add(shelter)
        await session.flush()
        print(self.format_progress("Shelters", len(shelter_ids), target, t0))
        return shelter_ids

    async def _generate_users(
        self, session: AsyncSession, role_map: dict[str, uuid.UUID]
    ) -> tuple[list[uuid.UUID], list[uuid.UUID], list[uuid.UUID], list[uuid.UUID], list[uuid.UUID]]:
        target = self.counts["users"]
        user_ids: list[uuid.UUID] = []
        vet_ids: list[uuid.UUID] = []
        foster_ids: list[uuid.UUID] = []
        volunteer_ids: list[uuid.UUID] = []
        donor_ids: list[uuid.UUID] = []

        t0 = time.perf_counter()
        for chunk_start in range(0, target, self.batch_size):
            chunk_end = min(chunk_start + self.batch_size, target)
            for i in range(chunk_start, chunk_end):
                u_id = uuid.uuid4()
                user_ids.append(u_id)
                created_at = self.random_past_date()
                is_deleted = self.rng.random() < 0.03

                # Role assignment distribution
                r_val = self.rng.random()
                if r_val < 0.05:
                    assigned_role = "VET_STAFF"
                    vet_ids.append(u_id)
                elif r_val < 0.15:
                    assigned_role = "FOSTER_PARENT"
                    foster_ids.append(u_id)
                elif r_val < 0.30:
                    assigned_role = "VOLUNTEER"
                    volunteer_ids.append(u_id)
                elif r_val < 0.60:
                    assigned_role = "DONOR"
                    donor_ids.append(u_id)
                else:
                    assigned_role = "PUBLIC_USER"

                u = User(
                    id=u_id,
                    email=f"user_{i}_{self.seed}@pawguard-scale.test",
                    phone=f"+91{self.rng.randint(7000000000, 9999999999)}",
                    full_name=f"Scale User {i}",
                    hashed_password=DUMMY_ARGON2_HASH,
                    is_active=not is_deleted,
                    is_verified=self.rng.random() > 0.1,
                    created_at=created_at,
                    deleted_at=created_at + timedelta(days=30) if is_deleted else None,
                )
                session.add(u)

                # Link user role
                ur = UserRole(user_id=u_id, role_id=role_map.get(assigned_role, role_map["PUBLIC_USER"]))
                session.add(ur)

                # Add notification preferences
                np = NotificationPreference(
                    user_id=u_id,
                    enable_push=True,
                    enable_email=True,
                    enable_sms=self.rng.random() > 0.5,
                )
                session.add(np)

            await session.flush()
            print(self.format_progress("Users", chunk_end, target, t0))

        if not vet_ids:
            vet_ids = user_ids[:5]
        if not foster_ids:
            foster_ids = user_ids[:10]
        if not volunteer_ids:
            volunteer_ids = user_ids[:10]
        if not donor_ids:
            donor_ids = user_ids[:20]

        return user_ids, vet_ids, foster_ids, volunteer_ids, donor_ids

    async def _generate_dogs(
        self, session: AsyncSession, shelter_ids: list[uuid.UUID]
    ) -> list[uuid.UUID]:
        target = self.counts["dogs"]
        dog_ids: list[uuid.UUID] = []
        statuses = [DogStatus.SHELTER, DogStatus.ADOPTED, DogStatus.FOSTERED, DogStatus.CLINIC, DogStatus.RESCUED]
        genders = [DogGender.MALE, DogGender.FEMALE]
        breeds = ["Indie", "Labrador Mix", "Beagle Cross", "German Shepherd Mix", "Terrier Mix"]

        t0 = time.perf_counter()
        for chunk_start in range(0, target, self.batch_size):
            chunk_end = min(chunk_start + self.batch_size, target)
            for i in range(chunk_start, chunk_end):
                d_id = uuid.uuid4()
                dog_ids.append(d_id)
                created_at = self.random_past_date()
                status = self.rng.choice(statuses)
                is_adoptable = status in (DogStatus.SHELTER, DogStatus.FOSTERED) and self.rng.random() > 0.2
                is_deleted = self.rng.random() < 0.02

                dog = DogProfile(
                    id=d_id,
                    registration_number=f"DOG-S{self.seed}-{i:07d}",
                    microchip_id=f"CHIP-S{self.seed}-{i:07d}" if self.rng.random() > 0.3 else None,
                    name=f"Doggo_{i}",
                    breed=self.rng.choice(breeds),
                    breed_classification=DogBreedClassification.MIX,
                    gender=self.rng.choice(genders),
                    is_spayed_neutered=self.rng.random() > 0.4,
                    age_months=self.rng.randint(2, 120),
                    weight=round(self.rng.uniform(5.0, 35.0), 2),
                    status=status,
                    shelter_facility_id=self.rng.choice(shelter_ids) if shelter_ids else None,
                    is_adoptable=is_adoptable,
                    is_quarantine_passed=self.rng.random() > 0.1,
                    created_at=created_at,
                    deleted_at=created_at + timedelta(days=60) if is_deleted else None,
                )
                session.add(dog)
            await session.flush()
            print(self.format_progress("Dogs", chunk_end, target, t0))

        return dog_ids

    async def _generate_medical(
        self, session: AsyncSession, dog_ids: list[uuid.UUID], vet_ids: list[uuid.UUID]
    ) -> None:
        target = self.counts["medical_records"]
        t0 = time.perf_counter()
        for chunk_start in range(0, target, self.batch_size):
            chunk_end = min(chunk_start + self.batch_size, target)
            for _i in range(chunk_start, chunk_end):
                d_id = self.rng.choice(dog_ids)
                v_id = self.rng.choice(vet_ids)
                exam_date = self.random_past_date()
                exam = ClinicalExam(
                    id=uuid.uuid4(),
                    dog_id=d_id,
                    vet_id=v_id,
                    exam_date=exam_date,
                    body_condition_score=self.rng.randint(3, 7),
                    triage_diagnosis="Routine health examination and parasite screening.",
                    created_at=exam_date,
                )
                session.add(exam)

                vac = VaccinationRecord(
                    id=uuid.uuid4(),
                    dog_id=d_id,
                    administered_by=v_id,
                    vaccine_name=self.rng.choice(["Rabies", "DHPP", "Bordetella", "Corona"]),
                    batch_number=f"VAC-BATCH-{self.rng.randint(100, 999)}",
                    administered_at=exam_date,
                    expires_at=exam_date + timedelta(days=365),
                    created_at=exam_date,
                )
                session.add(vac)
            await session.flush()
            print(self.format_progress("Medical Records", chunk_end, target, t0))

    async def _generate_adoptions(
        self, session: AsyncSession, dog_ids: list[uuid.UUID], user_ids: list[uuid.UUID]
    ) -> None:
        target = self.counts["adoptions"]
        statuses = [AdoptionStatus.SUBMITTED, AdoptionStatus.APPROVED, AdoptionStatus.COMPLETED, AdoptionStatus.REJECTED]
        t0 = time.perf_counter()
        for chunk_start in range(0, target, self.batch_size):
            chunk_end = min(chunk_start + self.batch_size, target)
            for _i in range(chunk_start, chunk_end):
                app_date = self.random_past_date()
                app = AdoptionApplication(
                    id=uuid.uuid4(),
                    dog_id=self.rng.choice(dog_ids),
                    adopter_id=self.rng.choice(user_ids),
                    status=self.rng.choice(statuses),
                    residential_status="owned",
                    has_landlord_approval=True,
                    has_yard_fence=self.rng.random() > 0.2,
                    household_members_count=self.rng.randint(1, 6),
                    created_at=app_date,
                )
                session.add(app)
            await session.flush()
            print(self.format_progress("Adoptions", chunk_end, target, t0))

    async def _generate_fosters(
        self, session: AsyncSession, dog_ids: list[uuid.UUID], foster_user_ids: list[uuid.UUID]
    ) -> None:
        target = self.counts["fosters"]
        t0 = time.perf_counter()
        for i in range(min(target, len(foster_user_ids))):
            f_id = uuid.uuid4()
            u_id = foster_user_ids[i]
            profile = FosterProfile(
                id=f_id,
                user_id=u_id,
                status=FosterStatus.APPROVED,
                max_capacity=self.rng.randint(1, 3),
                active_count=1,
                is_available=True,
                created_at=self.random_past_date(),
            )
            session.add(profile)

            placement = FosterPlacement(
                id=uuid.uuid4(),
                foster_id=f_id,
                dog_id=self.rng.choice(dog_ids),
                start_date=self.random_past_date().date(),
                is_active=self.rng.random() > 0.5,
                created_at=self.random_past_date(),
            )
            session.add(placement)
        await session.flush()
        print(self.format_progress("Foster Placements", min(target, len(foster_user_ids)), target, t0))

    async def _generate_volunteers(
        self, session: AsyncSession, volunteer_user_ids: list[uuid.UUID], shelter_ids: list[uuid.UUID]
    ) -> None:
        target = self.counts["volunteers"]
        t0 = time.perf_counter()
        for i in range(min(target, len(volunteer_user_ids))):
            v_id = uuid.uuid4()
            u_id = volunteer_user_ids[i]
            profile = VolunteerProfile(
                id=v_id,
                user_id=u_id,
                status=VolunteerStatus.ACTIVE,
                emergency_contact_name=f"Emergency Contact {i}",
                emergency_contact_phone=f"+91{self.rng.randint(7000000000, 9999999999)}",
                created_at=self.random_past_date(),
            )
            session.add(profile)

            shift_date = self.random_past_date()
            shift = VolunteerShift(
                id=uuid.uuid4(),
                shelter_facility_id=self.rng.choice(shelter_ids) if shelter_ids else None,
                role_name="Walking",
                start_at=shift_date,
                end_at=shift_date + timedelta(hours=3),
                capacity=5,
                created_at=shift_date,
            )
            session.add(shift)
        await session.flush()
        print(self.format_progress("Volunteer Profiles", min(target, len(volunteer_user_ids)), target, t0))

    async def _generate_donations(
        self, session: AsyncSession, donor_user_ids: list[uuid.UUID], dog_ids: list[uuid.UUID]
    ) -> None:
        target = self.counts["donations"]
        t0 = time.perf_counter()
        for chunk_start in range(0, target, self.batch_size):
            chunk_end = min(chunk_start + self.batch_size, target)
            for i in range(chunk_start, chunk_end):
                don_date = self.random_past_date()
                donation = Donation(
                    id=uuid.uuid4(),
                    donor_id=None,
                    dog_id=self.rng.choice(dog_ids) if self.rng.random() > 0.5 else None,
                    amount=self.rng.choice([500.0, 1000.0, 2500.0, 5000.0, 10000.0]),
                    currency="INR",
                    donation_type=DonationType.ONE_TIME,
                    status=DonationStatus.SUCCESS,
                    transaction_id=f"TXN-SCALE-{self.seed}-{i:07d}",
                    created_at=don_date,
                )
                session.add(donation)
            await session.flush()
            print(self.format_progress("Donations", chunk_end, target, t0))

    async def _generate_telemetry_logs(
        self, session: AsyncSession, user_ids: list[uuid.UUID]
    ) -> None:
        target_notifs = self.counts["notifications"]
        target_audits = self.counts["audit_logs"]

        t0 = time.perf_counter()
        for chunk_start in range(0, target_notifs, self.batch_size):
            chunk_end = min(chunk_start + self.batch_size, target_notifs)
            for i in range(chunk_start, chunk_end):
                sent_at = self.random_past_date()
                is_read = self.rng.random() > 0.3
                notif = Notification(
                    id=uuid.uuid4(),
                    user_id=self.rng.choice(user_ids),
                    title="Scale Update Alert",
                    body=f"Important system notification regarding activity reference {i}",
                    notification_type="general",
                    is_read=is_read,
                    read_at=sent_at + timedelta(minutes=15) if is_read else None,
                    sent_at=sent_at,
                    created_at=sent_at,
                )
                session.add(notif)
            await session.flush()
            print(self.format_progress("Notifications", chunk_end, target_notifs, t0))

        t1 = time.perf_counter()
        for chunk_start in range(0, target_audits, self.batch_size):
            chunk_end = min(chunk_start + self.batch_size, target_audits)
            for _i in range(chunk_start, chunk_end):
                log_time = self.random_past_date()
                audit = AuthAuditLog(
                    id=uuid.uuid4(),
                    event_type="login_success" if self.rng.random() > 0.2 else "profile_updated",
                    actor_id=self.rng.choice(user_ids),
                    ip_address=f"10.0.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}",
                    user_agent="PawGuard-ScaleLoadTest/1.0",
                    timestamp=log_time,
                )
                session.add(audit)
            await session.flush()
            print(self.format_progress("Audit Logs", chunk_end, target_audits, t1))


def main() -> None:
    parser = argparse.ArgumentParser(description="PawGuard Synthetic Scale Data Generator")
    parser.add_argument("--scale", choices=list(SCALE_PROFILES.keys()), default="test", help="Target user scale profile")
    parser.add_argument("--seed", type=int, default=12345, help="Deterministic random seed")
    parser.add_argument("--batch-size", type=int, default=2000, help="DB chunk insertion batch size")
    parser.add_argument("--dry-run", action="store_true", help="Calculate record counts and batches without writing to DB")
    parser.add_argument("--database-url", type=str, default="", help="Override database connection URL")

    args = parser.parse_args()
    settings = get_settings()
    db_url = args.database_url or settings.database_url

    generator = ScaleDataGenerator(
        db_url=db_url,
        scale=args.scale,
        seed=args.seed,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )
    asyncio.run(generator.run())


if __name__ == "__main__":
    main()
