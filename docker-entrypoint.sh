#!/bin/sh
set -e

# Apply database migrations before the app starts so a fresh/empty database is
# migrated before the lifespan's role seeding queries it. `alembic upgrade head`
# is a no-op when the schema is already current.
if [ "$SKIP_MIGRATIONS" = "true" ]; then
    echo "[docker-entrypoint] Skipping database migrations..."
else
    echo "[docker-entrypoint] Applying database migrations..."
    alembic upgrade head
fi

if [ "$SKIP_SEEDING" = "true" ]; then
    echo "[docker-entrypoint] Skipping test dog seeding..."
else
    echo "[docker-entrypoint] Seeding test dog profiles..."
    python scripts/seed_dogs.py
fi

exec "$@"
