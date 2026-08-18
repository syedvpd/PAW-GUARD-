# ADR-001: Backend Framework

## Status

Accepted

## Context

PawGuard requires a modern Python web framework for its backend API. The framework must support:
- Async/await for high-concurrency operations
- Automatic OpenAPI documentation
- Type safety with Pydantic
- Dependency injection
- Production-grade performance

## Decision

Use **FastAPI** as the backend framework.

## Alternatives Considered

### Django REST Framework
- **Pros**: Mature ecosystem, built-in admin, ORM
- **Cons**: Synchronous by default, heavier weight, less modern API design
- **Verdict**: Rejected due to async limitations and heavier footprint

### Flask
- **Pros**: Lightweight, flexible, large ecosystem
- **Cons**: No built-in async, requires more boilerplate, no automatic docs
- **Verdict**: Rejected due to lack of native async and type safety

### Starlette (raw)
- **Pros**: FastAPI's foundation, minimal overhead
- **Cons**: No automatic validation, no built-in docs, more manual setup
- **Verdict**: Rejected in favor of FastAPI's higher-level abstractions

### Litestar
- **Pros**: Modern, type-safe, good performance
- **Cons**: Smaller community, less mature ecosystem
- **Verdict**: Rejected due to community size and ecosystem maturity

## Consequences

### Positive
- Native async/await support
- Automatic OpenAPI/Swagger documentation
- Pydantic integration for request/response validation
- Dependency injection system
- Strong type safety
- High performance (comparable to Node.js/Go)
- Active community and ecosystem

### Negative
- Smaller ecosystem than Django
- Less mature than Django for enterprise applications
- Requires more setup for admin interface

## Implementation Notes

- FastAPI app created in `src/pawguard/main.py`
- Router structure follows modular pattern
- Dependencies injected via `Depends()` pattern
- OpenAPI schema customized for security schemes
- Middleware stack: CORS, TrustedHost, SecurityHeaders, RequestBodySize, Idempotency, RequestLogging, RequestID
