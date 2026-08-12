"""Quick diagnostic: test the veterinarian endpoint for a specific clinic.

Usage:
    .venv\\Scripts\\python.exe scripts/test_vet_endpoint.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from httpx import AsyncClient, ASGITransport
from pawguard.main import app


async def main() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        # 1. Get list of clinics
        r = await client.get("/api/v1/companion-pets/clinics")
        clinics = r.json().get("data", [])
        print(f"Total clinics: {len(clinics)}")
        if not clinics:
            print("  ERROR: No clinics returned!")
            return

        for clinic in clinics[:3]:
            cid = clinic["id"]
            name = clinic["name"]
            print(f"\nClinic: {name} ({cid})")

            # 2. Try vets endpoint - no auth (should get 403 or list)
            rv = await client.get(f"/api/v1/companion-pets/clinics/{cid}/veterinarians")
            print(f"  GET /veterinarians status : {rv.status_code}")
            body = rv.json()
            if rv.status_code == 200:
                vets = body.get("data", [])
                print(f"  Vets returned            : {len(vets)}")
                for v in vets:
                    print(f"    - {v.get('full_name')} ({v.get('email')})")
            else:
                print(f"  Response: {body}")


if __name__ == "__main__":
    asyncio.run(main())
