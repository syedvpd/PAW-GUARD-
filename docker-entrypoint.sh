#!/bin/sh
set -e

# Apply database migrations before the app starts so a fresh/empty database is
# migrated before the lifespan's role seeding queries it. `alembic upgrade head`
# is a no-op when the schema is already current.
echo "[docker-entrypoint] Applying database migrations..."
alembic upgrade head

exec "$@"
