"""Diagnostic: prints public table counts and column definitions for a target database."""

import asyncio

import asyncpg


async def main():
    db_url = "postgresql://postgres.ggzguyqptcedoudfkiev:pawguardstaging%402026@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    tables = [
        r[0] for r in await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    ]
    print(f"Public tables count: {len(tables)}")
    if "alembic_version" in tables:
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        print("Alembic current version:", version)
    else:
        print("No alembic_version table found")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
