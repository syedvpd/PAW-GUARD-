#!/bin/sh
set -e

# Apply database migrations before the app starts so a fresh/empty database is
# migrated before the lifespan's role seeding queries it. `alembic upgrade head`
# is a no-op when the schema is already current.
echo "[docker-entrypoint] Applying database migrations..."
alembic upgrade head

# Seed adoptable test dog profiles so the public adoption catalog (GET
# /api/v1/dogs) is never empty on a fresh/separate database. The script is
# idempotent: existing registration numbers are skipped.
echo "[docker-entrypoint] Seeding test dog profiles..."
python scripts/seed_dogs.py

exec "$@"
