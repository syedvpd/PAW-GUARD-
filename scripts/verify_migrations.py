"""Verify both Supabase databases have the same migration applied."""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pawguard.core.config import get_settings


def check_database(label: str, url: str) -> None:
    if not url:
        print(f"SKIP [{label}]: No URL configured.")
        return

    print(f"CHECK [{label}]: {url[:55]}...")
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_section_option(
        cfg.config_ini_section,
        "sqlalchemy.connect_args",
        '{"statement_cache_size": 0}',
    )
    try:
        command.check(cfg)
        print(f"OK    [{label}]: Schema matches migrations.")
    except Exception as e:
        if "No new upgrade operations detected" in str(e):
            print(f"OK    [{label}]: Schema matches migrations (check passed).")
        else:
            print(f"FAIL  [{label}]: {e}")


def main() -> None:
    settings = get_settings()
    check_database("Backend DB", settings.database_url)
    check_database("Frontend DB", settings.database_url_frontend)


if __name__ == "__main__":
    main()
