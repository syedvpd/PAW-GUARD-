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
    print("Duplicates with ('home_check', 'approved', 'completed'):", len(rows))
    for r in rows:
        print(dict(r))
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
