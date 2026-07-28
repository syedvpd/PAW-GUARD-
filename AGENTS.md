# AGENTS.md

# PawGuard Backend Engineering Constitution

Version: 1.0

Status: MANDATORY

Applies To:
- Claude
- ChatGPT
- Codex
- Cursor
- GitHub Copilot
- Windsurf
- All Human Developers

---

# ENGINEERING MISSION

This backend is the single source of truth for the entire PawGuard ecosystem.

Supported Clients

- Public Website
- Admin Portal
- Rescue Staff Mobile Application
- Executive Mobile Application

Every engineering decision SHALL prioritise:

1. Correctness
2. Security
3. Reliability
4. Maintainability
5. Scalability
6. Performance

The objective is to build a backend capable of serving millions of users without requiring architectural redesign.

---

# AI EXECUTION CONTRACT

Before generating ANY code the AI SHALL:

✓ Understand the complete request.

✓ Search the existing implementation.

✓ Identify the owning module.

✓ Identify reusable services.

✓ Identify reusable repositories.

✓ Identify reusable utilities.

✓ Identify existing schemas.

✓ Identify existing models.

✓ Identify permissions.

✓ Identify validation rules.

✓ Identify transaction boundaries.

✓ Identify audit requirements.

✓ Identify logging requirements.

✓ Identify affected tests.

Only after completing this analysis may code be generated.

Never generate code blindly.

---

# ABSOLUTE ENGINEERING RULES

These rules SHALL NEVER be violated.

RULE-001

Business logic SHALL NOT exist inside API Routers.

RULE-002

Repositories SHALL NOT contain business decisions.

RULE-003

Services SHALL own business behaviour.

RULE-004

Routers SHALL only:

- authenticate
- authorise
- validate
- call services
- return responses

Nothing else.

RULE-005

Every endpoint SHALL be production ready.

RULE-006

Every feature SHALL remain compatible with all supported clients.

RULE-007

Generated code SHALL follow existing project conventions.

Never introduce a second implementation style.

---

# ARCHITECTURE CONTRACT

Mandatory request flow

Client

↓

Router

↓

Service

↓

Repository

↓

Database

Never allow

Router

↓

Database

Never place SQL inside API routes.

Never bypass the service layer.

Never introduce circular dependencies.

Never couple unrelated domains.

---

# DOMAIN OWNERSHIP

Every module owns its own business rules.

No module may directly modify another module's internal state.

Communication between domains SHALL happen through services or approved application workflows.

Never tightly couple modules.

---

# CODE GENERATION STANDARD

Every generated code change SHALL be:

- typed
- readable
- testable
- maintainable
- asynchronous where appropriate
- deterministic

Never optimise for fewer lines of code.

Optimise for clarity.

---

# REUSE POLICY

Before creating ANY:

- Service
- Repository
- Schema
- Utility
- Validator
- Dependency
- Middleware

Search the codebase first.

Reuse existing implementations whenever possible.

Duplication is prohibited.

---

# SECURITY CONTRACT

Every endpoint SHALL enforce:

Authentication

↓

Authorisation

↓

Permission Validation

↓

Input Validation

↓

Business Validation

↓

Execution

↓

Audit Logging

Never expose:

- passwords
- tokens
- secrets
- credentials
- stack traces
- internal errors

Never trust frontend validation.

Backend validation is mandatory.

---

# DATABASE CONTRACT

Always:

- use migrations
- preserve integrity
- use foreign keys
- use indexes
- use transactions
- use UUID identifiers
- use optimistic locking where required

Never:

- modify production data manually
- hard delete operational records
- bypass migrations

Database consistency is mandatory.

---

# TRANSACTION RULES

Keep transactions:

- short
- atomic
- deterministic

Never perform:

- email sending
- SMS
- push notifications
- HTTP calls
- file uploads

inside database transactions.

---

# BACKGROUND TASKS

Move long-running work to background workers.

Examples:

- email
- SMS
- push notification
- report generation
- image processing
- PDF generation
- analytics

Never block HTTP requests with long-running work.

---

# API CONTRACT

Every endpoint SHALL:

- be versioned
- validate requests
- validate responses
- return standard response models
- support pagination where appropriate
- support filtering where appropriate
- support sorting where appropriate

Never introduce breaking API changes without approval.

---

# PERFORMANCE CONTRACT

Optimise for:

- low latency
- minimal queries
- asynchronous execution
- efficient memory usage

Avoid:

- N+1 queries
- duplicate queries
- unnecessary joins
- unnecessary API calls
- loading unnecessary data

Every query SHALL have a reason.

---

# CACHE CONTRACT

Only cache data that benefits performance.

Never cache:

- security decisions
- permissions without invalidation
- transactional writes

Always define cache invalidation.

---

# LOGGING CONTRACT

Every request SHALL generate:

- Request ID
- User ID
- Module
- Endpoint
- Latency
- Status Code

Never log sensitive information.

Structured logging only.

---

# ERROR CONTRACT

Never expose:

- SQL errors
- stack traces
- framework internals
- implementation details

Return meaningful API errors.

---

# TESTING CONTRACT

Every change SHALL preserve:

- unit tests
- integration tests
- API tests

Never delete tests to satisfy CI.

---

# DOCUMENTATION CONTRACT

Whenever behaviour changes:

Update:

- OpenAPI
- README
- Documentation
- Examples

Documentation SHALL match implementation.

---

# GIT CONTRACT

AI SHALL NEVER:

- commit
- push
- merge
- rebase
- force push
- delete branches

unless explicitly instructed.

---

# REVIEW CHECKLIST

Before completing work verify:

✓ Architecture preserved

✓ Security preserved

✓ Permissions enforced

✓ Validation added

✓ Logging preserved

✓ Tests updated

✓ Documentation updated

✓ No duplicated logic

✓ No breaking changes

✓ No unnecessary abstractions

---

# DEFINITION OF DONE

A feature is complete only when:

✓ Business logic implemented

✓ Validation complete

✓ Permissions enforced

✓ Logging complete

✓ Tests passing

✓ Documentation updated

✓ Architecture preserved

✓ Performance considered

✓ Security reviewed

✓ Production ready

---

# FINAL PRINCIPLE

Every change SHALL leave the backend:

- safer
- cleaner
- faster
- easier to maintain
- easier to test
- easier to scale

If any requested change violates this constitution, the AI MUST explain the conflict before generating code.

This document takes precedence over personal coding preferences.