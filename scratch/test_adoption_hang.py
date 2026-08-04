import asyncio
import sys
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from httpx import AsyncClient
from pawguard.main import create_app
from pawguard.db.session import get_db
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from pawguard.core.config import get_settings

async def main():
    print("Initializing app...")
    app = create_app()
    
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=True, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    async with session_factory() as db_session:
        from tests.conftest import FakeRedis, FakeArqPool
        from pawguard.redis.client import get_redis
        from pawguard.workers.pool import get_arq_pool
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_redis] = lambda: FakeRedis()
        app.dependency_overrides[get_arq_pool] = lambda: FakeArqPool()
        
        from httpx import ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            print("1 & 2. Registering and authenticating...")
            email = "hangtest@example.com"
            # Cleanup user if exists
            from sqlalchemy import text
            await db_session.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
            await db_session.commit()
            
            from tests.auth_helpers import register_and_auth
            headers = await register_and_auth(client, db_session, email=email)
            print("Logged in successfully. Headers:", headers)
            print("Logged in successfully. Headers:", headers)
            
            print("3. Creating dog...")
            payload = {
                "name": "AdoptDog", "breed": "Lab", "gender": "male", 
                "estimated_age": "2y", "weight": 20, "color": "black", 
                "temperament": "friendly", "is_adoptable": True, "is_quarantine_passed": True
            }
            resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
            print("Dog creation status:", resp.status_code)
            dog_id = resp.json()["data"]["id"]
            
            print("4. Granting clearance...")
            resp = await client.post(f"/api/v1/medical/clearance/{dog_id}", headers=headers)
            print("Clearance status:", resp.status_code)
            
            print("5. Applying for adoption...")
            payload = {
                "dog_id": dog_id,
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 1,
                "pet_care_experience": "Some experience"
            }
            resp = await client.post("/api/v1/adoptions", json=payload, headers=headers)
            print("Adoption application status:", resp.status_code)
            app_id = resp.json()["data"]["id"]
            
            print("6. Updating status to screening...")
            resp = await client.put(f"/api/v1/adoptions/{app_id}", json={"status": "screening"}, headers=headers)
            print("Screening update status:", resp.status_code)
            
            print("7. Updating status to interview...")
            resp = await client.put(f"/api/v1/adoptions/{app_id}", json={"status": "interview"}, headers=headers)
            print("Interview update status:", resp.status_code)
            
            print("8. Updating status to home_check...")
            resp = await client.put(f"/api/v1/adoptions/{app_id}", json={"status": "home_check"}, headers=headers)
            print("Home check update status:", resp.status_code)
            
            print("9. Updating status to approved...")
            resp = await client.put(f"/api/v1/adoptions/{app_id}", json={"status": "approved"}, headers=headers)
            print("Approved update status:", resp.status_code)
            
    await engine.dispose()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
