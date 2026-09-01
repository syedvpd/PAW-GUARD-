"""Master seed script for PawGuard.

Orchestrates all individual domain seeders in the correct relational dependency
order (roles first, then clinics/dogs, then stories/sponsorships/appointments).

Usage:
    .venv\\Scripts\\python.exe scripts/seed_all.py
"""

import asyncio
import sys
from pathlib import Path

# Add project directories to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_blogs_and_sponsorships import main as seed_blogs
from scripts.seed_dogs import seed_dogs
from scripts.seed_found_reports import main as seed_found_reports
from scripts.seed_pet_appointments import main as seed_appointments
from scripts.seed_roles_and_permissions import main as seed_roles
from scripts.seed_success_stories import seed_success_stories
from scripts.seed_veterinarians import main as seed_vets
from scripts.seed_veterinary_partners import main as seed_partners
from scripts.seed_volunteer_data import main as seed_volunteers


async def run_all() -> None:
    print("=========================================================")
    print(" Starting Master Seeding Process for PawGuard DB")
    print("=========================================================\n")

    try:
        print("--> Seeding 1/9: Roles & Permissions...")
        await seed_roles()

        print("\n--> Seeding 2/9: Operational Users & Volunteer Module Data...")
        await seed_volunteers()

        print("\n--> Seeding 3/9: Veterinary Partners (Clinics)...")
        await seed_partners()

        print("\n--> Seeding 4/9: Veterinarians & Memberships...")
        await seed_vets()

        print("\n--> Seeding 5/9: Adoptable Dogs...")
        await seed_dogs()

        print("\n--> Seeding 6/9: Success Stories...")
        await seed_success_stories()

        print("\n--> Seeding 7/9: Blogs & Sponsorships...")
        await seed_blogs()

        print("\n--> Seeding 8/9: Found-Animal Reports...")
        await seed_found_reports()

        print("\n--> Seeding 9/9: Pet Appointments & Companion Pets...")
        await seed_appointments()

        print("\n=========================================================")
        print(" SUCCESS: Master Seeding Completed for all tables!")
        print("=========================================================")
    except Exception as exc:
        print(f"\n[ERROR] Master seeding failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all())
