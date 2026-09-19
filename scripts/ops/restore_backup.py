"""Operational: restore a Super Admin backup (pawguard-backup-v1 .json.gz) into an EMPTY database.

Usage:
    alembic upgrade <alembic_version printed below>   # against the target DATABASE_URL
    python scripts/ops/restore_backup.py path/to/pawguard-backup-YYYYMMDD-HHMMSS.json.gz

The target must be freshly migrated to the backup's alembic revision and hold no rows;
the script refuses to write into a database that already has users.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, select, text

import pawguard.api.v1.router  # noqa: F401  registers every model on Base.metadata
from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.admin.backup import read_backup, restore_backup
from pawguard.modules.auth.models import User


async def main(path: str) -> None:
    document = read_backup(Path(path).read_bytes())
    print(f"Backup created {document['created_at']}, alembic {document['alembic_version']}")
    async with AsyncSessionLocal() as db:
        current = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        if current != document["alembic_version"]:
            sys.exit(f"Target is at {current}; migrate it to {document['alembic_version']} first.")
        if (await db.execute(select(func.count(User.id)))).scalar_one():
            sys.exit("Target database already has users; restore only into an empty database.")
        restored = await restore_backup(db, document)
        await db.commit()
    for table, count in restored.items():
        print(f"{table}: {count}")
    print(f"Restored {sum(restored.values())} rows. Everyone must sign in again.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
