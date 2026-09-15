import asyncio
import asyncpg


async def main():
    db_url = "postgresql://postgres.ggzguyqptcedoudfkiev:pawguardstaging%402026@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    rows = await conn.fetch("""
        SELECT dog_id, count(*)
        FROM adoption_applications
        WHERE status IN ('home_check', 'approved', 'completed') AND deleted_at IS NULL
        GROUP BY dog_id
        HAVING count(*) > 1;
    """)
    print("Duplicates count:", len(rows))
    for r in rows:
        dog_id = r["dog_id"]
        print(f"Dog {dog_id} has {r['count']} active applications:")
        apps = await conn.fetch("""
            SELECT id, adopter_id, status, created_at, updated_at
            FROM adoption_applications
            WHERE dog_id = $1 AND status IN ('home_check', 'approved', 'completed') AND deleted_at IS NULL
            ORDER BY created_at;
        """, dog_id)
        for app in apps:
            print("  ", dict(app))
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
