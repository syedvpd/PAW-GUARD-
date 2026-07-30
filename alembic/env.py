import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from pawguard.core.config import get_settings
from pawguard.db.base import Base

# Import all module models so they register on Base.metadata for autogenerate.
from pawguard.modules.auth import models as auth_models  # noqa: F401
from pawguard.modules.rescue import models as rescue_models  # noqa: F401
from pawguard.modules.dog import models as dog_models  # noqa: F401
from pawguard.modules.adoption import models as adoption_models  # noqa: F401
from pawguard.modules.volunteer import models as volunteer_models  # noqa: F401
from pawguard.modules.foster import models as foster_models  # noqa: F401
from pawguard.modules.donation import models as donation_models  # noqa: F401
from pawguard.modules.lost_found import models as lost_found_models  # noqa: F401
from pawguard.modules.medical import models as medical_models  # noqa: F401
from pawguard.modules.shelter import models as shelter_models  # noqa: F401
from pawguard.modules.inventory import models as inventory_models  # noqa: F401
from pawguard.modules.fleet import models as fleet_models  # noqa: F401
from pawguard.modules.grievance import models as grievance_models  # noqa: F401
from pawguard.modules.notifications import models as notification_models  # noqa: F401
from pawguard.modules.portal import models as portal_models  # noqa: F401
from pawguard.modules.finance import models as finance_models  # noqa: F401
from pawguard.modules.storage import models as storage_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# Read original ini file value to detect overrides from scripts.
ini_path = config.config_file_name
ini_url = ""
if ini_path:
    import configparser
    parser = configparser.ConfigParser()
    parser.read(ini_path)
    ini_url = parser.get(config.config_ini_section, "sqlalchemy.url", fallback="")
current_url = config.get_main_option("sqlalchemy.url")
if current_url == ini_url or not current_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"statement_cache_size": 0},
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
