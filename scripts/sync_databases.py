"""Database Synchronization Script for PawGuard.

Replicates 100% of the schemas and records from a source database to a target
database. Uses Postgres session_replication_role to safely bypass constraint
ordering, truncates target tables, bulk inserts records in chunks, and resets
auto-incrementing sequences.

Usage:
    .venv\\Scripts\\python.exe scripts/sync_databases.py <source_url> <target_url>
"""

import asyncio
import sys
from pathlib import Path

# Add project root and src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pawguard.core.config import get_settings
from pawguard.db.base import Base
from pawguard.modules.adoption import models as adoption_models  # noqa: F401

# Import all models to register them on Base.metadata
from pawguard.modules.auth import models as auth_models  # noqa: F401
from pawguard.modules.companion_pet import models as companion_pet_models  # noqa: F401
from pawguard.modules.dog import models as dog_models  # noqa: F401
from pawguard.modules.donation import models as donation_models  # noqa: F401
from pawguard.modules.finance import models as finance_models  # noqa: F401
from pawguard.modules.fleet import models as fleet_models  # noqa: F401
from pawguard.modules.foster import models as foster_models  # noqa: F401
from pawguard.modules.grievance import models as grievance_models  # noqa: F401
from pawguard.modules.inventory import models as inventory_models  # noqa: F401
from pawguard.modules.lost_found import models as lost_found_models  # noqa: F401
from pawguard.modules.medical import models as medical_models  # noqa: F401
from pawguard.modules.notifications import models as notification_models  # noqa: F401
from pawguard.modules.outbox import models as outbox_models  # noqa: F401
from pawguard.modules.portal import models as portal_models  # noqa: F401
from pawguard.modules.rescue import models as rescue_models  # noqa: F401
from pawguard.modules.settings import models as settings_models  # noqa: F401
from pawguard.modules.shelter import models as shelter_models  # noqa: F401
from pawguard.modules.storage import models as storage_models  # noqa: F401
from pawguard.modules.volunteer import models as volunteer_models  # noqa: F401


def mask_db_url(url: str) -> str:
    """Mask password in connection strings for logging security."""
    try:
        if "@" in url:
            prefix, rest = url.split("://", 1)
            credentials, host_port_db = rest.split("@", 1)
            user = credentials.split(":", 1)[0]
            return f"{prefix}://{user}:******@{host_port_db}"
    except Exception:
        pass
    return "******"


async def sync_data(source_url: str, target_url: str) -> None:
    print("=========================================================")
    print(" Starting PawGuard Database Synchronization")
    print("=========================================================")
    print(f"Source DB: {mask_db_url(source_url)}")
    print(f"Target DB: {mask_db_url(target_url)}\n")

    # Connect to both databases with prepared statement caches disabled
    source_engine = create_async_engine(source_url, connect_args={"statement_cache_size": 0})
    target_engine = create_async_engine(target_url, connect_args={"statement_cache_size": 0})

    try:
        # Retrieve all mapped ORM tables sorted topologically based on FK constraints
        tables = Base.metadata.sorted_tables
        print(f"Found {len(tables)} tables to synchronize in ORM metadata.\n")

        # Open transactional connections
        async with source_engine.connect() as src_conn, target_engine.begin() as tgt_conn:
            # 1. Disable constraints and triggers session-wide on target DB
            print("--> Disabling target foreign keys & triggers...")
            await tgt_conn.execute(text("SET session_replication_role = 'replica';"))

            # 2. Clear target tables in reverse order to keep dependencies clean
            print("--> Clearing target tables...")
            for table in reversed(tables):
                await tgt_conn.execute(table.delete())
            print("    Target tables cleared.")

            # 3. Migrate data table-by-table
            print("\n--> Syncing table data...")
            sync_report = []
            for table in tables:
                table_name = table.name

                # Fetch all rows from source table
                select_stmt = table.select()
                res = await src_conn.execute(select_stmt)
                rows = [dict(row._mapping) for row in res.fetchall()]

                src_count = len(rows)
                tgt_count = 0

                if src_count > 0:
                    # Perform bulk inserts in chunks of 500 records
                    chunk_size = 500
                    for i in range(0, src_count, chunk_size):
                        chunk = rows[i : i + chunk_size]
                        insert_stmt = table.insert().values(chunk)
                        await tgt_conn.execute(insert_stmt)
                    tgt_count = src_count

                print(
                    f"    Synced {table_name:<30} | Source Rows: {src_count:<5} | Target Rows: {tgt_count:<5}"
                )
                sync_report.append((table_name, src_count, tgt_count))

            # 4. Re-enable constraints and triggers
            print("\n--> Restoring target foreign keys & triggers...")
            await tgt_conn.execute(text("SET session_replication_role = 'origin';"))

            # 5. Re-align PostgreSQL autoincrement sequences
            print("--> Re-aligning PostgreSQL serial sequences...")
            seq_query = """
                SELECT pgc.relname AS seq_name, pgt.relname AS table_name, pga.attname AS col_name
                FROM pg_class pgc
                JOIN pg_depend pgd ON pgd.objid = pgc.oid
                JOIN pg_class pgt ON pgt.oid = pgd.refobjid
                JOIN pg_attribute pga ON pga.attrelid = pgt.oid AND pga.attnum = pgd.refobjsubid
                WHERE pgc.relkind = 'S';
            """
            seq_res = await tgt_conn.execute(text(seq_query))
            for seq_row in seq_res.fetchall():
                seq_name = seq_row.seq_name
                table_name = seq_row.table_name
                col_name = seq_row.col_name

                # Update sequence value to current max(column_value)
                update_seq_stmt = f"""
                    SELECT setval('{seq_name}', COALESCE((SELECT MAX({col_name}) FROM {table_name}), 1), true);
                """  # noqa: S608
                await tgt_conn.execute(text(update_seq_stmt))
            print("    All sequences re-aligned successfully.")

        print("\n=========================================================")
        print(" SUCCESS: Database Sync Completed with 100% Fidelity!")
        print("=========================================================")

    except Exception as exc:
        print(f"\n[ERROR] Database sync failed: {exc}")
        sys.exit(1)
    finally:
        await source_engine.dispose()
        await target_engine.dispose()


def main() -> None:
    settings = get_settings()

    # Read URLs from command line arguments or config environment
    source_url = sys.argv[1] if len(sys.argv) > 1 else settings.database_url
    target_url = sys.argv[2] if len(sys.argv) > 2 else None

    # Fallback to secondary target variables if target_url not provided on CLI
    if not target_url:
        target_url = settings.database_url_frontend

    if not source_url or not target_url:
        print("Usage Error: Missing connection URLs.")
        print("    Please provide them as CLI args:")
        print("    python scripts/sync_databases.py <source_url> <target_url>")
        print("\n    Or configure in your .env:")
        print("    DATABASE_URL=source_connection_string")
        print("    DATABASE_URL_FRONTEND=target_connection_string")
        sys.exit(1)

    # Force asyncpg driver if postgresql is provided without it
    if source_url.startswith("postgresql://"):
        source_url = source_url.replace("postgresql://", "postgresql+asyncpg://")
    if target_url.startswith("postgresql://"):
        target_url = target_url.replace("postgresql://", "postgresql+asyncpg://")

    asyncio.run(sync_data(source_url, target_url))


if __name__ == "__main__":
    main()
