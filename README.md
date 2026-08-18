# PawGuard Backend

Enterprise backend platform for PawGuard — Rescue, Shelter, Medical, Adoption, Foster,
Volunteers, Inventory, Donations, Finance, Analytics and Operations.

**Single source of truth** for the entire PawGuard ecosystem:

- Public Website (Next.js)
- Admin Portal (React)
- Public Flutter App
- Staff Flutter App
- Executive / Admin Flutter App

---

## Architecture

Modular monolith following **Domain-Driven Design** and **Clean Architecture** principles.

### Request flow

```
Client → Router → Service → Repository → Database
```

- **Routers** — authenticate, authorise, validate, call services, return responses.
- **Services** — own all business behaviour and domain logic.
- **Repositories** — data access only, no business decisions.
- **Core** — cross-cutting concerns (config, logging, security, exceptions, pagination, etc.).

Business logic **never** lives in routers or repositories. See [AGENTS.md](AGENTS.md) for the full engineering constitution.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.13 |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.x (async) |
| Database | PostgreSQL 17 |
| Migrations | Alembic |
| Cache / Queue | Redis + ARQ |
| Validation | Pydantic v2 |
| Auth | JWT (RS256) + Argon2id |
| MFA | TOTP (pyotp) |
| File Storage | AWS S3 |
| Background Jobs | ARQ Worker |
| Logging | structlog |
| Serialisation | orjson |
| Containerisation | Docker |
| Package Manager | uv |

---

## Modules

| # | Module | Status |
|---|---|---|
| 1 | `auth` | Authentication, authorisation, RBAC, permissions, MFA, audit trail |
| 2 | `dog` | Dog profiles, medical history, behavior, media | Dog microchip auto-generation, duplicate intake prevention, adoption directory |
| 3 | `rescue` | Rescue intake, triage, field operations |
| 4 | `medical` | Medical records, vaccinations, surgeries, treatments |
| 5 | `adoption` | Adoption applications, approvals, contracts, follow-ups |
| 6 | `foster` | Foster applications, placements, returns |
| 7 | `volunteer` | Volunteer registration, scheduling, hours, training |
| 8 | `inventory` | Inventory tracking, stock levels, orders |
| 9 | `donation` | Donations, pledges, receipts, donor management |
| 10 | `fleet` | Fleet vehicles, maintenance, trips, fuel |
| 11 | `notifications` | In-app, email, push notification delivery |
| 12 | `storage` | File uploads, S3 integration, media processing |
| 13 | `portal` | Portal configuration, public-facing endpoints |
| 14 | `shelter` | Shelter management, capacity, room assignments |
| 15 | `settings` | Global system settings, feature flags |
| 16 | `grievance` | Complaint and grievance management |
| 17 | `lost_found` | Lost and found pet matching |
| 18 | `admin` | Admin dashboard, system administration |
| 19 | `companion_pet` | Owner pets, privacy-safe QR tags, clinics, appointments, medical uploads, reminders |

---

## Project Structure

```
pawguard-backend/
├── .github/workflows/     # CI/CD pipelines
├── alembic/               # Database migrations
├── scripts/               # Seed scripts, migration utilities
├── secrets/               # JWT key pair (dev only)
├── src/
│   └── pawguard/
│       ├── api/           # API versioned routers
│       │   └── v1/
│       ├── core/          # Config, exceptions, logging, middleware, security
│       ├── db/            # Session, base model, mixins, Unit of Work
│       ├── modules/       # Domain modules (18 modules)
│       │   ├── auth/
│       │   ├── dog/
│       │   ├── rescue/
│       │   ├── medical/
│       │   ├── adoption/
│       │   ├── foster/
│       │   ├── volunteer/
│       │   ├── inventory/
│       │   ├── donation/
│       │   ├── fleet/
│       │   ├── notifications/
│       │   ├── storage/
│       │   ├── portal/
│       │   ├── shelter/
│       │   ├── settings/
│       │   ├── grievance/
│       │   ├── lost_found/
│       │   └── admin/
│       ├── redis/         # Redis client
│       ├── services/      # Cross-domain services (audit, email, cache, etc.)
│       ├── workers/       # ARQ background workers
│       └── main.py        # FastAPI application factory
├── tests/                 # Test suite
├── .env.example           # Environment template
├── docker-compose.yml     # Local Postgres + Redis
├── Dockerfile             # Production image
├── pyproject.toml          # Dependencies, tool config
├── AGENTS.md              # Engineering constitution
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker & Docker Compose
- OpenSSL (for JWT key generation)

### 1. Clone and enter the repository

```bash
git clone https://github.com/your-org/pawguard-backend.git
cd pawguard-backend
```

### 2. Environment setup

```bash
cp .env.example .env
```

Edit `.env` to match your local configuration. The defaults work out of the box with the provided `docker-compose.yml`.

### 3. Generate JWT key pair

```bash
mkdir -p secrets
openssl genrsa -out secrets/private_key.pem 2048
openssl rsa -in secrets/private_key.pem -pubout -out secrets/public_key.pem
```

> **Production:** Use a secrets manager (e.g. AWS Secrets Manager, HashiCorp Vault).

### 4. (Optional) Run the Backend inside Docker
If you prefer running the backend API and worker inside Docker containers (connecting to Supabase database):
```bash
docker compose up -d
```
Otherwise, you can skip this step and run the services directly on your host machine as detailed below.

### 5. Install dependencies

```bash
uv sync --extra dev
```

### 6. Run database migrations

```bash
uv run alembic upgrade head
```

### 7. Start the API

```bash
uv run uvicorn pawguard.main:app --reload --host 0.0.0.0 --port 8000
```

### 8. Open API docs

Visit [http://localhost:8000/docs](http://localhost:8000/docs) (local and staging only).

---

## Environment Variables

Key configuration is managed through `.env`. See `src/pawguard/core/config.py` for the full list.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://pawguard:pawguard@localhost:5432/pawguard` | Database connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `ENVIRONMENT` | `local` | `local`, `staging`, or `production` |
| `JWT_PRIVATE_KEY_PATH` | `./secrets/private_key.pem` | Path to RS256 private key |
| `JWT_PUBLIC_KEY_PATH` | `./secrets/public_key.pem` | Path to RS256 public key |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `GOOGLE_OAUTH_CLIENT_ID` | _(empty)_ | Google OAuth app client id; ID tokens whose aud does not match are rejected. OAuth login fails closed when unset. |
| `APPLE_OAUTH_CLIENT_ID` | _(empty)_ | Apple Sign-in client id (services id); audience-verified. OAuth login fails closed when unset. |

---

## Database

### Migrations with Alembic

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Create a new migration (autogenerate)
uv run alembic revision --autogenerate -m "description"

# Rollback one step
uv run alembic downgrade -1

# Check for migration drift (CI)
uv run alembic check

# View history
uv run alembic history
```

### Seed Data

```bash
# Seed roles and permissions
uv run python -m scripts.seed_roles_and_permissions
```

---

## Testing

```bash
# Run all tests with coverage
uv run pytest --cov=src/ --cov-report=term-missing -v

# Run specific test file
uv run pytest tests/test_auth.py -v

# Run tests matching a keyword
uv run pytest -k "test_login" -v
```

> **Windows / Git Bash:** if you run tests from Git Bash and hit
> `AssertionError: A path prefix must start with '/'` at import time, an
> exported `API_V1_PREFIX=/api/v1` is being mangled by MSYS path conversion
> into `C:/Program Files/Git/api/v1` when native Python is spawned. Fix it
> with `unset API_V1_PREFIX` (the `.env` value is already `/api/v1`) or
> `export MSYS_NO_PATHCONV=1` before running pytest.
>
> Integration tests require a migrated PostgreSQL instance: point
> `DATABASE_URL` / `DATABASE_URL_FRONTEND` in `.env` at a local database and
> run `uv run alembic upgrade head` first.

### Quality Gates

```bash
# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/

# Security audit
uv run bandit -c pyproject.toml -r src/

# All checks
uv run ruff check src/ tests/ && uv run mypy src/ && uv run bandit -c pyproject.toml -r src/
```

---

## API Documentation

When running in `local` or `staging` environments:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

### Health Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness summary |
| `GET /live` | Process is up |
| `GET /ready` | Dependencies (DB, Redis) are reachable |

### Companion Pet APIs

Authenticated endpoints are versioned under `/api/v1/companion-pets`. Owners are
scoped to their own pets; clinic staff require an active clinic membership and
patient access; administrators can manage all records.

- `POST/GET /companion-pets` and `GET/PATCH/DELETE /companion-pets/{pet_id}`
- `POST /companion-pets/{pet_id}/medical-files/upload-url` and medical-record endpoints
- `POST/GET /companion-pets/{pet_id}/safety-tag` for hashed-token QR tags
- `POST /companion-pets/safety-tag/scan` for the rate-limited, PII-free public scan flow
- `GET/POST /companion-pets/clinics` and clinic membership administration
- `POST/GET /companion-pets/appointments` plus detail, confirm, and cancel actions
- `POST/GET /companion-pets/{pet_id}/reminders` for vaccination and medication reminders

Reminder delivery runs through the ARQ worker and the existing in-app
`NotificationService`; the unique delivery key makes retries idempotent.

---

## Background Workers

```bash
# Start the ARQ worker
uv run arq pawguard.workers.arq_worker.WorkerSettings
```

Workers handle async tasks: email delivery, push notifications, report generation, image processing.

---

## Deployment

### Docker

```bash
# Build the image
docker build -t pawguard-backend .

# Run with environment
docker run -d --name pawguard-api \
  -p 8000:8000 \
  --env-file .env \
  pawguard-backend
```

### Docker Compose (production variant)

Use the production-specific Docker Compose configuration:
```bash
docker compose -f docker-compose.prod.yml up -d
```
This starts the backend API, the ARQ background worker, and the Redis cache/queue, while connecting to your remote database (e.g. Supabase).

### Render

Email and notification delivery depends on the ARQ background worker consuming
jobs from Redis. Two options:

#### Two services (paid)

**Web service** + **Background Worker service**, both pointing at the same repo:

1. **Web service** — start command:
   ```bash
   uvicorn pawguard.main:app --host 0.0.0.0 --port 10000
   ```
2. **Worker service** — start command (same code, same env vars):
   ```bash
   arq pawguard.workers.arq_worker.WorkerSettings
   ```

Both services must share these env vars (in addition to `DATABASE_URL`,
`JWT_PRIVATE_KEY_PEM`/`JWT_PUBLIC_KEY_PEM`, `MAIL_*`, etc.):

| Key | Value |
|---|---|
| `REDIS_URL` | Render Redis internal URL, e.g. `rediss://default:TOKEN@redact...:6379/0` (TLS `rediss://` is supported) |
| `ENVIRONMENT` | `production` |
| `WEB_APP_URL` / `ADMIN_APP_URL` | Your live frontend URLs |

If `REDIS_URL` is wrong or unreachable, the app **still starts** and HTTP stays
up — but jobs are silently dropped (`arq_pool_unreachable_falling_back_to_noop`)
and email will not be delivered. Check the worker logs for `email_sent` to
confirm delivery.

#### Free tier (single service, no paid Background Worker)

Render's free web service can run the API **and** the ARQ worker in one process
via `pawguard.serve` — no separate Background Worker service (which has no free
tier) is needed:

```bash
# Render web service Start Command
uv run python -m pawguard.serve
```

This launches uvicorn (API, port from `$PORT`) and the ARQ worker as concurrent
asyncio tasks in the same process. If Redis is unreachable the API still serves
requests and the worker degrades to a no-op loop. Set `REDIS_URL` to your Redis
internal URL (e.g. `redis://red-...:6379`).

### GitHub Actions CI/CD

Three workflows are provided:

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci.yml` | Push to main/develop, PRs | Lint, type check, security scan, test with coverage |
| `docker-build.yml` | Push to main, tags | Build and push Docker image to GHCR |
| `alembic-check.yml` | Pull requests | Validate no migration drift |

---

## Contributing

1. Read [AGENTS.md](AGENTS.md) — the engineering constitution is mandatory.
2. Follow the architecture: `Router → Service → Repository → Database`.
3. Business logic belongs in **services**, not routers or repositories.
4. Every endpoint must be production-ready with auth, validation, and audit logging.
5. Run all quality gates before submitting a PR:
   ```bash
   uv run ruff check src/ tests/
   uv run mypy src/
   uv run bandit -c pyproject.toml -r src/
   uv run pytest
   ```
6. Ensure migrations are autogenerated and committed for model changes.
7. Never commit secrets, tokens, or credentials.

---

## Documentation

Comprehensive documentation is available in the `docs/` directory:

| Documentation | Location | Purpose |
|---|---|---|
| Architecture | [`docs/architecture/`](docs/architecture/) | System design, application layers, caching, background jobs |
| API Reference | [`docs/api/`](docs/api/) | Endpoint documentation, request/response schemas |
| Database | [`docs/database/`](docs/database/) | Schema, relationships, migrations, indexes, constraints |
| Security | [`docs/security/`](docs/security/) | Authentication, authorization, rate limiting, audit logging |
| Business Flows | [`docs/flows/`](docs/flows/) | Rescue, adoption, foster, medical workflows |
| Decisions | [`docs/decisions/`](docs/decisions/) | Architecture Decision Records (ADRs) |
| Deployment | [`docs/deployment/`](docs/deployment/) | Render, Supabase, Docker deployment guides |
| Testing | [`docs/testing/`](docs/testing/) | Testing strategy and quality gates |
| Platform | [`docs/platform/`](docs/platform/) | Cross-platform architecture, API contracts |

Each module also has its own `README.md` in `src/pawguard/modules/<module>/README.md`.

---

## License

Proprietary — All rights reserved. Unauthorized copying, distribution, or use is prohibited.

---

## Engineering Constitution

See [AGENTS.md](AGENTS.md) for the full engineering constitution covering:

- Absolute engineering rules
- Architecture contract
- Domain ownership
- Code generation standards
- Reuse policy
- Security contract
- Database contract
- Transaction rules
- API contract
- Performance contract
- Logging and error contracts
- Testing and documentation contracts
- Definition of done
