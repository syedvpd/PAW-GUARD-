import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect("postgresql://postgres:postgres_secure_pass@localhost:5432/postgres")
    dbs = [r[0] for r in await conn.fetch("SELECT datname FROM pg_database")]
    print("Databases on postgres:", dbs)
    if "pawguard_test" not in dbs:
        await conn.execute("CREATE DATABASE pawguard_test")
        print("Created database pawguard_test")
    else:
        print("Database pawguard_test already exists")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
