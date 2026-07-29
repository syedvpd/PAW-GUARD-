# PawGuard Backend

Enterprise backend platform for PawGuard — Rescue, Shelter, Medical, Adoption, Foster,
Volunteers, Inventory, Donations, Finance, Analytics and Operations.

Single source of truth for: Public Website (Next.js), Admin Portal (React), Public Flutter App,
Staff Flutter App, Executive/Admin Flutter App.

## Stack

FastAPI · Python 3.13 · SQLAlchemy 2.x (async) · PostgreSQL 17 · Alembic · Redis · Pydantic v2 ·
ARQ · JWT (RS256) · Argon2id · AWS S3 · Docker · uv

## Architecture

Modular monolith following Domain-Driven Design and Clean Architecture principles.

Mandatory request flow: `Client -> Router -> Service -> Repository -> Database`.
Business logic never lives in routers or repositories — see [AGENTS.md](AGENTS.md) for the
full engineering constitution.

## Local development

1. Copy environment file:

   ```bash
   cp .env.example .env
   ```

2. Generate an RS256 keypair for JWT signing (dev only — use a secrets manager in production):

   ```bash
   mkdir -p secrets
   openssl genrsa -out secrets/private_key.pem 2048
   openssl rsa -in secrets/private_key.pem -pubout -out secrets/public_key.pem
   ```

3. Start Postgres and Redis:

   ```bash
   docker compose up -d
   ```

4. Install dependencies (uv):

   ```bash
   uv sync --extra dev
   ```

5. Run migrations:

   ```bash
   uv run alembic upgrade head
   ```

6. Start the API:

   ```bash
   uv run uvicorn pawguard.main:app --reload
   ```

7. Docs available at `http://localhost:8000/docs` (local/staging only).

## Quality gates

```bash
uv run ruff check .
uv run mypy src
uv run bandit -r src
uv run pytest
```

## Health endpoints

- `GET /health` — liveness summary
- `GET /live` — process is up
- `GET /ready` — dependencies (DB, Redis) are reachable

## Project layout

See [AGENTS.md](AGENTS.md) for the mandatory architecture contract and `src/pawguard/` for the
module layout (`core/`, `db/`, `redis/`, `modules/auth/`, `services/`, `workers/`, `api/`).
