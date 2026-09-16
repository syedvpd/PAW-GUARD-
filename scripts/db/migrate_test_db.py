"""Repeatable: applies migrations against the local test PostgreSQL database."""

import os
import sys

from alembic import command
from alembic.config import Config


def main():
    db_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "postgresql+asyncpg://postgres:postgres_secure_pass@localhost:5432/pawguard_test"
    )
    os.environ["DATABASE_URL"] = db_url
    print(f"Applying Alembic upgrade head to: {db_url}")
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    print("Migration completed successfully!")


if __name__ == "__main__":
    main()
