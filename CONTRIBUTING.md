# Contributing to PawGuard Backend

Thank you for contributing to PawGuard. This document covers the standards and
processes required for all contributions.

## Engineering Constitution

**Read [AGENTS.md](AGENTS.md) before making any changes.** The engineering
constitution is mandatory for all contributors — human and AI alike.

## Architecture Rules

Every change must follow the mandatory request flow:

```
Client → Router → Service → Repository → Database
```

- **Routers** authenticate, authorise, validate, call services, return responses.
- **Services** own all business behaviour and domain logic.
- **Repositories** handle data access only — no business decisions.
- **Business logic never lives in routers or repositories.**

See [docs/architecture/application.md](docs/architecture/application.md) for
detailed layer responsibilities.

## Code Standards

### Python

- Python 3.13+
- Type hints on all function signatures
- Pydantic v2 for request/response validation
- Async/await for all database and I/O operations
- Follow existing code conventions — no second implementation style

### Linting and Formatting

```bash
# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Type check
uv run mypy src/
```

### Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Modules | `snake_case` | `rescue`, `dog_profile` |
| Classes | `PascalCase` | `RescueRequest`, `DogProfile` |
| Functions | `snake_case` | `verify_request`, `dispatch_team` |
| Constants | `UPPER_SNAKE` | `RESCUE_STATUS_ACTIVE` |
| API paths | `kebab-case` | `/rescue-requests`, `/dog-profiles` |
| DB tables | `snake_case` | `rescue_requests`, `dog_profiles` |

## Module Structure

Every module follows this structure:

```
src/pawguard/modules/<module>/
├── __init__.py
├── models.py          # SQLAlchemy ORM models
├── schemas.py         # Pydantic request/response schemas
├── repository.py      # Data access layer
├── service.py         # Business logic (RULE-003)
├── router.py          # API endpoints (RULE-004)
└── README.md          # Module documentation
```

### RULE-004: Router Responsibilities

Routers SHALL only:

1. Authenticate the request
2. Authorise the user
3. Validate input
4. Call the appropriate service
5. Return the response

Nothing else. No business logic in routers.

### RULE-003: Service Responsibilities

Services SHALL own all business behaviour:

- Business validation
- State transitions
- Domain events
- Audit logging
- Cache invalidation
- Background job dispatch

## Security Requirements

Every endpoint must enforce:

1. **Authentication** — JWT validation
2. **Authorization** — RBAC permission check
3. **Input validation** — Pydantic schema validation
4. **Business validation** — Service-layer rules
5. **Audit logging** — Record the action

Never expose:
- Passwords or tokens
- Stack traces or internal errors
- SQL errors or implementation details

See [docs/security/](docs/security/) for detailed security documentation.

## Database Rules

- Use Alembic migrations for all schema changes
- Preserve data integrity with foreign keys
- Use UUID primary keys
- Use soft deletes (never hard delete operational records)
- Add appropriate indexes
- Use transactions for atomic operations

```bash
# Create a migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head
```

## Testing Requirements

All changes must preserve existing tests and include new tests where
appropriate.

```bash
# Run all tests
uv run pytest --cov=src/ --cov-report=term-missing -v

# Run specific module tests
uv run pytest tests/test_rescue.py -v
```

## Commit Guidelines

- Write clear, concise commit messages
- Reference issue numbers where applicable
- Keep commits focused on single changes
- Never commit secrets, tokens, or credentials

### Commit Message Format

```
type(scope): description

- detail 1
- detail 2
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes following the standards above
3. Run all quality gates:
   ```bash
   uv run ruff check src/ tests/
   uv run mypy src/
   uv run pytest
   ```
4. Update relevant documentation
5. Submit PR with clear description
6. Address review feedback

## Documentation Requirements

Every behavior-changing code update must update the relevant documentation:

- Module changes → update `src/pawguard/modules/<module>/README.md`
- API changes → update `docs/api/<module>.md`
- Architecture changes → update `docs/architecture/`
- Security changes → update `docs/security/`

## Prohibited Patterns

- Business logic in routers or repositories
- Circular dependencies between modules
- Hardcoded secrets or credentials
- Skipping authorization checks
- Silent exception swallowing
- N+1 queries
- Breaking API changes without approval

## Getting Help

- Review [AGENTS.md](AGENTS.md) for the full engineering constitution
- Check [docs/architecture/](docs/architecture/) for system design
- See [docs/flows/](docs/flows/) for business workflow documentation
