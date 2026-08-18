# API Contract Conventions

## Overview

PawGuard follows consistent API conventions across all endpoints. This document describes the contract standards.

## Base URL

```
/api/v1
```

## HTTP Methods

| Method | Purpose | Idempotent |
|--------|---------|------------|
| `GET` | Read resource(s) | Yes |
| `POST` | Create resource | No |
| `PUT` | Full update | Yes |
| `PATCH` | Partial update | Yes |
| `DELETE` | Delete resource | Yes |

## URL Naming

### Resources (plural nouns)
```
/rescue          # Collection
/rescue/{id}     # Specific resource
```

### Actions (verbs)
```
/rescue/{id}/verify     # Action on resource
/rescue/{id}/dispatch   # Action on resource
```

### Nested Resources
```
/rescue/{id}/reports    # Sub-resource
/rescue/{id}/dispatch   # Sub-resource
```

## Request Headers

### Required
```
Authorization: Bearer <token>
Content-Type: application/json
```

### Optional
```
X-Client-Type: web|mobile|admin
X-Request-ID: <uuid>
```

## Response Headers

```
Content-Type: application/json
X-Request-ID: <uuid>
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 9
X-RateLimit-Reset: 1640995200
```

## Status Codes

### Success
| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `204` | No Content (successful delete) |

### Client Errors
| Code | Meaning |
|------|---------|
| `400` | Bad Request (validation error) |
| `401` | Unauthorized (invalid/missing token) |
| `403` | Forbidden (insufficient permissions) |
| `404` | Not Found |
| `409` | Conflict (duplicate, state conflict) |
| `422` | Unprocessable Entity (validation) |
| `429` | Too Many Requests (rate limit) |

### Server Errors
| Code | Meaning |
|------|---------|
| `500` | Internal Server Error |
| `503` | Service Unavailable |

## Pagination

### Query Parameters
```
?page=1&per_page=20&sort=created_at&order=desc
```

### Response
```json
{
  "data": [...],
  "meta": {
    "total": 100,
    "page": 1,
    "per_page": 20,
    "total_pages": 5
  }
}
```

## Filtering

### Query Parameters
```
?status=active&severity=critical&is_urgent=true
```

### Search
```
?search=keyword
```

## Sorting

### Query Parameters
```
?sort=created_at&order=desc
```

### Multi-field Sorting
```
?sort=severity,created_at&order=desc,asc
```

## Error Response Format

```json
{
  "success": false,
  "data": null,
  "message": "Validation failed",
  "errors": [
    {
      "field": "email",
      "message": "Invalid email format"
    }
  ]
}
```

## Validation Errors

### Pydantic Validation
```json
{
  "success": false,
  "data": null,
  "message": "Validation failed",
  "errors": [
    {"field": "email", "message": "value is not a valid email address"},
    {"field": "password", "message": "String should have at least 8 characters"}
  ]
}
```

### Business Validation
```json
{
  "success": false,
  "data": null,
  "message": "Cannot verify request in status: dispatched"
}
```

## Authentication

### Token Types
- `access_token`: Short-lived (15 min)
- `refresh_token`: Long-lived (30 days)

### Token Format
```
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

### Cookie Format (Web)
```
access_token=eyJhbGciOiJSUzI1NiIs...; HttpOnly; Secure; SameSite=Strict
refresh_token=...; HttpOnly; Secure; SameSite=Strict
```

## Idempotency

### Write Operations
- POST: Idempotency key via `IdempotencyMiddleware`
- PUT/PATCH/DELETE: Naturally idempotent

### Idempotency Key
```
X-Idempotency-Key: <uuid>
```

## Request Body

### JSON
```json
Content-Type: application/json
```

### Form Data
```
Content-Type: application/x-www-form-urlencoded
```

### Multipart
```
Content-Type: multipart/form-data
```

## File Uploads

### Presigned URL Flow
1. Request presigned URL: `POST /storage/presign`
2. Upload directly to S3
3. Confirm upload: `POST /storage/confirm`

### Direct Upload
```
Content-Type: multipart/form-data
```

## Webhooks

### Outgoing
- Payment gateway webhooks
- Configured per provider

### Incoming
- Not currently implemented

## Versioning

### URL Versioning
```
/api/v1/...
/api/v2/... (future)
```

### Backward Compatibility
- New fields added without breaking existing clients
- Deprecated fields marked with `deprecated: true`
- Removal requires major version bump

## Rate Limiting

### Headers
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 9
X-RateLimit-Reset: 1640995200
```

### 429 Response
```json
{
  "success": false,
  "data": null,
  "message": "Too many requests. Please try again later."
}
```

## CORS

### Allowed Origins
```
Access-Control-Allow-Origin: https://your-frontend.vercel.app
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, Authorization, X-Client-Type
```

## Content Types

### Request
- `application/json` (default)
- `multipart/form-data` (file upload)

### Response
- `application/json` (default)
- `text/csv` (export)
- `application/pdf` (export)
- `text/plain` (metrics)
