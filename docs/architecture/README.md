# PawGuard Backend Architecture Documentation

Version: 1.0
Status: Current
Last Updated: 2026-08-18

---

## Purpose

This directory contains the authoritative architecture documentation for the PawGuard backend platform. Every document is derived from the actual source code in `src/pawguard/` and reflects the implemented system, not aspirational design.

## Audience

- Backend engineers onboarding to the codebase
- Frontend/mobile engineers integrating with the API
- DevOps engineers deploying and operating the platform
- Security auditors reviewing system design
- Client stakeholders evaluating technical capability

## Document Index

| Document | Scope | Key Topics |
|----------|-------|------------|
| [system.md](./system.md) | Full system architecture | Deployment topology, technology stack, request flow, infrastructure |
| [application.md](./application.md) | Application layer | Module structure, service/repository pattern, middleware stack, dependency injection |
| [database.md](./database.md) | Data architecture | Schema design, ORM patterns, migrations, read/write splitting, sharding |
| [caching.md](./caching.md) | Caching strategy | Redis client, CacheService, RBAC cache, idempotency, distributed locks |
| [background-jobs.md](./background-jobs.md) | Background processing | ARQ worker, outbox pattern, scheduled jobs, retry strategy |
| [integrations.md](./integrations.md) | External services | FCM push, S3 storage, email delivery, payment gateway, OAuth providers |

## Technology Stack

| Layer | Technology | Version Constraint |
|-------|-----------|-------------------|
| Language | Python | >= 3.13 |
| Framework | FastAPI | >= 0.115.0 |
| ORM | SQLAlchemy (async) | >= 2.0.36 |
| Database | PostgreSQL (asyncpg) | >= 0.30.0 |
| Migrations | Alembic | >= 1.14.0 |
| Cache / Queue | Redis | >= 5.2.0 |
| Background Jobs | ARQ | >= 0.26.0 |
| Validation | Pydantic | >= 2.9.0 |
| Password Hashing | Argon2id (argon2-cffi) | >= 23.1.0 |
| JWT | RS256 (pyjwt) | >= 2.10.0 |
| MFA | TOTP (pyotp) | >= 2.9.0 |
| Object Storage | AWS S3 / Supabase (boto3) | >= 1.35.0 |
| Push Notifications | Firebase Cloud Messaging | >= 6.5.0 |
| Email | Brevo API / SMTP (Jinja2) | >= 3.1.4 |
| Payments | Razorpay (provider-agnostic) | >= 2.0.0 |
| Structured Logging | structlog | >= 24.4.0 |
| PDF Generation | ReportLab | >= 4.2.0 |
| Container Runtime | Docker | - |

## Source Layout

```
src/pawguard/
    main.py                  # Application factory, lifespan, health checks
    api/v1/router.py         # Aggregates all module routers under /api/v1
    core/                    # Cross-cutting: config, security, middleware, metrics
    db/                      # Engine, session, mixins, audit, sharding
    redis/                   # Async Redis client with graceful degradation
    services/                # Shared services: cache, email, push, storage, audit
    modules/                 # Domain modules (27 modules)
    workers/                 # ARQ worker, job definitions, Redis pool
    templates/email/         # Jinja2 email templates
```

## Engineering Principles

All architecture decisions follow the PawGuard Backend Engineering Constitution (`AGENTS.md`):

1. **Correctness** over speed of delivery
2. **Security** as a non-negotiable baseline
3. **Reliability** through graceful degradation
4. **Maintainability** via strict layer separation
5. **Scalability** through stateless services and horizontal readiness

## Related Documents

- `AGENTS.md` - Engineering constitution and mandatory rules
- `README.md` - Project overview and setup instructions
- `.env.example` - Environment variable reference
- `docker-compose.yml` - Local development topology
- `docker-compose.prod.yml` - Production topology
