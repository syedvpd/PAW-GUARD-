"""Repeatable: applies Alembic migrations across configured PostgreSQL databases."""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pawguard.core.config import get_settings

ALEMBIC_CFG_PATH = Path(__file__).resolve().parent.parent / "alembic.ini"


def run_migration(label: str, database_url: str) -> None:
    if not database_url:
        print(f"SKIP [{label}]: No database URL configured.")
        return

    print(f"RUN  [{label}]: Applying migrations to {database_url[:50]}...")
    alembic_cfg = Config(str(ALEMBIC_CFG_PATH))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(alembic_cfg, "head")
    print(f"DONE [{label}]: Migrations applied successfully.\n")


def main() -> None:
    settings = get_settings()

    run_migration("Backend DB", settings.database_url)
    run_migration("Frontend DB", settings.database_url_frontend)

    print("All migrations applied to all configured databases.")


if __name__ == "__main__":
    main()
