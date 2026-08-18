# API Common Conventions

## Overview

This document describes the standard patterns, conventions, and shared schemas used across all PawGuard API endpoints.

---

## Response Envelope

Every API response follows a consistent envelope format defined in `src/pawguard/core/responses.py`.

### Success Response

```json
{
  "success": true,
  "data": { ... },
  "message": "Optional human-readable message."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `true` for successful responses |
| `data` | object/array/null | Response payload (type varies by endpoint) |
| `message` | string/null | Optional status message |

### Error Response

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Validation failed for 'body.email': Value is not a valid email address.",
    "details": [...]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `false` for error responses |
| `error.code` | string | Machine-readable error code |
| `error.message` | string | Human-readable error description |
| `error.details` | array/null | Additional validation or context details |

---

## Pagination

All list endpoints return paginated results using offset-based pagination defined in `src/pawguard/core/pagination.py`.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number (1-indexed) |
| `page_size` | integer | 20 | Items per page (1-100) |

### Paginated Response

```json
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "total": 150,
    "page": 1,
    "page_size": 20,
    "total_pages": 8
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `meta.total` | integer | Total number of matching records |
| `meta.page` | integer | Current page number |
| `meta.page_size` | integer | Items per page |
| `meta.total_pages` | integer | Total number of pages |

---

## Sorting

All list endpoints support sorting via query parameters defined in `src/pawguard/core/search.py`.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sort_by` | string | `created_at` | Field to sort by |
| `sort_order` | string | `desc` | Sort direction: `asc` or `desc` |

### Allowed Sort Fields

Each endpoint defines its own set of allowed sort fields. Attempting to sort by an unsupported field returns a `422` error with the list of valid options.

---

## Search

List endpoints that support full-text search accept a `search` query parameter. The search performs case-insensitive matching across one or more fields using `ILIKE` with wildcard patterns.

### Example

```
GET /api/v1/dogs?search=barnaby
```

Searches across `name`, `breed`, and `registration_number` fields.

---

## Filtering

List endpoints support field-level filtering via query parameters. Filter parameters are validated against the endpoint's allowed filter set.

### Example

```
GET /api/v1/dogs?status=shelter&gender=male&temperament=friendly
```

---

## Bulk Operations

Bulk operations are defined in `src/pawguard/core/bulk.py` and provide consistent patterns for batch status updates and soft-deletes.

### Bulk Status Update

**`POST /{module}/bulk/status-update`**

**Request Body:**

```json
{
  "ids": ["uuid-1", "uuid-2", "uuid-3"],
  "status": "new_status"
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `ids` | UUID[] | 1-100 items |
| `status` | string | Module-specific status value |

**Response:**

```json
{
  "success": true,
  "data": {
    "message": "3 record(s) status updated.",
    "updated_count": 3
  }
}
```

### Bulk Delete

**`POST /{module}/bulk/delete`**

**Request Body:**

```json
{
  "ids": ["uuid-1", "uuid-2", "uuid-3"]
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "message": "3 record(s) deleted.",
    "deleted_count": 3
  }
}
```

---

## Soft Delete Pattern

All operational records use soft delete (defined in `src/pawguard/db/mixins.py`). Records are never hard-deleted. The `deleted_at` column is set to the timestamp of deletion; null indicates an active record.

Soft-deleted records are excluded from all queries by default.

---

## Authentication

### JWT Bearer Token

```
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

### HttpOnly Cookies (Web Clients)

Web clients receive tokens as HttpOnly cookies:
- `access_token` - Short-lived JWT (default: 60 minutes)
- `refresh_token` - Long-lived refresh token (default: 30 days)

When the `X-Client-Type: web` header is present, the API sets cookies and omits tokens from the JSON response body.

---

## Rate Limiting

Rate limits are applied per-endpoint and tracked by client IP address. Limits are enforced via the `rate_limit` dependency.

### Standard Limits

| Category | Limit | Window |
|----------|-------|--------|
| Registration | 5 | 1 hour |
| Login | 10 | 1 minute |
| Token Refresh | 30 | 1 minute |
| Password Reset | 5 | 1 hour |
| MFA Verify | 10 | 5 minutes |
| Rescue Report | 5 | 1 minute |
| Public Rescue Report | 5 | 1 minute |
| Media Upload | 10 | 1 minute |
| Dog QR Scan | 20 | 1 minute |
| Rescue Status Lookup | 10 | 1 minute |

When rate limited, the API returns `429 Too Many Requests` with a `TOO_MANY_REQUESTS` error code.

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `APP_ERROR` | 400 | General application error |
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_FAILED` | 422 | Request validation failed |
| `CONFLICT` | 409 | Resource already exists or state conflict |
| `UNAUTHORIZED` | 401 | Authentication required or invalid |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `TOO_MANY_REQUESTS` | 429 | Rate limit exceeded |
| `HTTP_ERROR` | Various | HTTP-level errors |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

---

## Validation

All request bodies are validated using Pydantic models. Validation errors return a `422` response with detailed field-level error information.

### Password Requirements

All passwords must meet the following criteria:
- Minimum 10 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit

---

## Audit Trail

Every mutating operation records an audit entry in the `auth_audit_logs` table with:
- `user_id` - Who performed the action
- `event_type` - What was done (e.g., `dog_registered`, `rescue_dispatched`)
- `ip_address` - Client IP address
- `event_metadata` - Additional context (old/new values, notes)
- `before_state` / `after_state` - Structured state snapshots for state transitions

---

## UUID Identifiers

All primary keys and foreign keys use UUIDs (v4). UUIDs are generated client-side or server-side using `uuid.uuid4()` and stored as PostgreSQL UUID type.

### Example UUIDs

```
550e8400-e29b-41d4-a716-446655440000
```

---

## Timestamps

All timestamps use ISO 8601 format with timezone information:

```
2026-08-18T10:30:00Z
```

The `created_at` and `updated_at` columns are automatically managed by the `TimestampMixin`.

---

## Content-Type

All request and response payloads use `application/json` unless otherwise specified (e.g., binary responses for QR images).

---

## CORS

The API supports cross-origin requests from configured origins. Credentials are allowed. All methods and headers are permitted.

---

## API Versioning

All endpoints are versioned under the `/api/v1` prefix. The version prefix is configurable via the `API_V1_PREFIX` environment variable.

Breaking changes will introduce a new version prefix (e.g., `/api/v2`). Non-breaking additions (new fields, new endpoints) are added to the current version without changes.
