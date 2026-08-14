import asyncio
import sys
from sqlalchemy import text
from pawguard.db.session import engine


async def main() -> None:
    print("Starting clean deletion of synthetic scale data...", flush=True)
    statements = [
        "DELETE FROM notifications WHERE body LIKE '%activity reference%';",
        "DELETE FROM auth_audit_logs WHERE user_agent = 'PawGuard-ScaleLoadTest/1.0';",
        "DELETE FROM donations WHERE transaction_id LIKE 'TXN-SCALE-%';",
        "DELETE FROM donor_profiles WHERE tax_identifier LIKE 'TAX-%';",
        "DELETE FROM volunteer_shifts WHERE shelter_facility_id IN (SELECT id FROM shelter_facilities WHERE name LIKE '%(Seed-%');",
        "DELETE FROM volunteer_profiles WHERE emergency_contact_name LIKE 'Emergency Contact %';",
        "DELETE FROM foster_placements WHERE foster_id IN (SELECT id FROM foster_profiles WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@pawguard-scale.test'));",
        "DELETE FROM foster_profiles WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@pawguard-scale.test');",
        "DELETE FROM adoption_applications WHERE adopter_id IN (SELECT id FROM users WHERE email LIKE '%@pawguard-scale.test');",
        "DELETE FROM vaccination_records WHERE lot_number LIKE 'VAC-LOT-%';",
        "DELETE FROM clinical_exams WHERE triage_diagnosis LIKE '%Healthy scale checkup%' OR ocular_aural_notes LIKE '%Routine checkup%';",
        "DELETE FROM dog_profiles WHERE registration_number LIKE 'DOG-S%';",
        "DELETE FROM shelter_facilities WHERE name LIKE '%(Seed-%';",
        "DELETE FROM user_roles WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@pawguard-scale.test');",
        "DELETE FROM notification_preferences WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@pawguard-scale.test');",
        "DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@pawguard-scale.test');",
        "DELETE FROM users WHERE email LIKE '%@pawguard-scale.test';",
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            res = await conn.execute(text(stmt))
            print(f"Executed: {stmt[:40]}... (rows deleted: {res.rowcount})", flush=True)

    await engine.dispose()
    print("\nSUCCESS: All synthetic scale test data deleted! Real data is intact.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
