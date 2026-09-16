"""Diagnostic: verifies partial unique index definitions on adoption applications."""

import asyncio

import asyncpg


async def main():
    db_url = "postgresql://postgres.ggzguyqptcedoudfkiev:pawguardstaging%402026@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
    conn = await asyncpg.connect(db_url, statement_cache_size=0)

    # 1. Inspect adoption_applications indexes
    rows = await conn.fetch("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'adoption_applications'
        ORDER BY indexname;
    """)
    print("=== ADOPTION_APPLICATIONS INDEXES ===")
    for r in rows:
        print(f"Index: {r['indexname']}")
        print(f"  Def: {r['indexdef']}")

    # 2. Inspect dog_profiles indexes
    rows = await conn.fetch("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'dog_profiles' AND (indexname LIKE '%kennel%' OR indexname LIKE '%uq%')
        ORDER BY indexname;
    """)
    print("\n=== DOG_PROFILES KENNEL/UQ INDEXES ===")
    for r in rows:
        print(f"Index: {r['indexname']}")
        print(f"  Def: {r['indexdef']}")

    # 3. Inspect foster_placements indexes
    rows = await conn.fetch("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'foster_placements'
        ORDER BY indexname;
    """)
    print("\n=== FOSTER_PLACEMENTS INDEXES ===")
    for r in rows:
        print(f"Index: {r['indexname']}")
        print(f"  Def: {r['indexdef']}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
