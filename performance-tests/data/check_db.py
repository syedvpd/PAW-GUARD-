import asyncio
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select
from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.auth.models import User, Role
from pawguard.modules.companion_pet.models import CompanionPet
from pawguard.modules.medical.models import VetClinic, Appointment

async def main():
    async with AsyncSessionLocal() as db:
        res_users = await db.execute(select(User))
        users = res_users.scalars().all()
        print(f"Total Users: {len(users)}")
        
        roles_count = {}
        for u in users:
            for r in u.roles:
                roles_count[r.name] = roles_count.get(r.name, 0) + 1
        print("Role breakdown:", roles_count)
        
        for u in users[:15]:
            roles = [r.name for r in u.roles]
            print(f"User: {u.id} | Email: {u.email} | Roles: {roles} | Active: {u.is_active} | Verified: {u.is_verified}")

        res_pets = await db.execute(select(CompanionPet))
        pets = res_pets.scalars().all()
        print(f"Total Companion Pets: {len(pets)}")
        for p in pets[:5]:
            print(f"Pet ID: {p.id} | Name: {p.name} | Owner ID: {p.owner_id}")

        res_clinics = await db.execute(select(VetClinic))
        clinics = res_clinics.scalars().all()
        print(f"Total Vet Clinics: {len(clinics)}")

if __name__ == "__main__":
    asyncio.run(main())
