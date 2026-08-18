# PawGuard API Documentation

## Overview

The PawGuard API is a RESTful service built with FastAPI, providing the backend for the entire PawGuard ecosystem including the Public Website, Admin Portal, Rescue Staff Mobile Application, and Executive Mobile Application.

**Base URL:** `https://api.pawguard.com/api/v1`

**Authentication:** JWT Bearer tokens via HTTP header or HttpOnly cookies.

**Content-Type:** `application/json` for all requests and responses.

---

## API Versioning

All endpoints are versioned under the `/api/v1` prefix. Breaking changes will introduce a new version prefix (`/api/v2`).

---

## Endpoint Groups

| Module | Prefix | Description | Documentation |
|--------|--------|-------------|---------------|
| Authentication | `/auth` | Login, registration, MFA, OAuth, sessions | [authentication.md](authentication.md) |
| Rescue | `/rescue` | Emergency incident reporting, dispatch, tracking | [rescue.md](rescue.md) |
| Dogs | `/dogs` | Dog profiles, weight tracking, QR tags | [dogs.md](dogs.md) |
| Medical | `/medical` | Clinical exams, treatments, vaccinations, prescriptions | [medical.md](medical.md) |
| Adoption | `/adoptions` | Applications, scoring, follow-ups | [adoption.md](adoption.md) |
| Shelter | `/shelter` | Facilities, sections, kennels, transfers | [shelter.md](shelter.md) |
| Fleet | `/fleet` | Vehicles, maintenance, equipment, fuel logs | [fleet.md](fleet.md) |

---

## Common Patterns

All API conventions (pagination, errors, response formats, bulk operations) are documented in [common.md](common.md).

---

## Health Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Application health check |
| GET | `/live` | Liveness probe (returns `alive`) |
| GET | `/ready` | Readiness probe (checks DB and Redis connectivity) |

---

## OpenAPI Specification

The full OpenAPI 3.1 specification is available at `/openapi.json` when documentation is enabled in the environment.

---

## Rate Limiting

Rate limits are applied per-endponent and tracked by client IP address. Limits are documented per endpoint in the module-specific files.

| Endpoint Category | Typical Limit |
|-------------------|---------------|
| Registration | 5 requests / hour |
| Login | 10 requests / minute |
| Token Refresh | 30 requests / minute |
| Password Reset | 5 requests / hour |
| Rescue Reports | 5 requests / minute |
| General CRUD | Varies by endpoint |

---

## Authentication Flow

1. Register via `POST /auth/register` (email + password)
2. Verify email via the link sent to the registered email
3. Login via `POST /auth/login` to receive access + refresh tokens
4. Use the access token in the `Authorization: Bearer <token>` header
5. Refresh expired access tokens via `POST /auth/refresh`

Web clients receive tokens as HttpOnly cookies. Mobile clients receive tokens in the JSON response body.

---

## Role-Based Access Control (RBAC)

Permissions are enforced on every endpoint via the `require_permission` dependency. Permission codes follow the pattern `module:action` (e.g., `rescue:create`, `shelter:update`, `medical:read`).

Common permission prefixes:
- `rescue:*` - Rescue operations (create, read, update, verify, dispatch, execute, delete)
- `shelter:*` - Shelter management (read, update)
- `medical:*` - Medical records (create, read, update, delete, clearance)
- `adoption:*` - Adoption processing (read, process)
- `vehicle:*` - Fleet management (read, update)
- `safety_tag:manage` - Safety Tag provisioning
- `system:admin` - Full system administration
