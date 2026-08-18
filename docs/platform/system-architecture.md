# Cross-Platform Architecture

## Overview

PawGuard backend serves multiple client platforms through a unified API. This document describes the cross-platform architecture.

## Supported Clients

| Client | Platform | Description |
|--------|----------|-------------|
| Public Website | Web (React/Next.js) | Public-facing adoption, rescue reporting |
| Admin Portal | Web (React/Vite) | Staff management interface |
| Rescue Staff App | Mobile (Flutter) | Field agent operations |
| Executive App | Mobile (Flutter) | Executive dashboard and reporting |

## API Architecture

### Versioned API
```
/api/v1/...
```

All endpoints are versioned to support multiple client versions simultaneously.

### Unified Backend
Single backend serves all clients:
- Same authentication system
- Same business logic
- Same data models
- Client-specific response formatting

## Client Type Detection

### Header-Based Detection
```python
CLIENT_TYPE_HEADER = "X-Client-Type"
```

Values:
- `web` - Web applications
- `mobile` - Mobile applications
- `admin` - Admin portal

### Usage
```python
client_type: str | None = Header(default=None, alias=CLIENT_TYPE_HEADER)
is_web = client_type == ClientType.WEB.value
```

## Authentication by Client

### Web Clients
- Tokens stored in httponly, secure cookies
- CSRF protection via SameSite=strict
- Automatic token refresh via cookies

### Mobile Clients
- Tokens returned in response body
- Stored in secure storage (Keychain/Keystore)
- Manual token refresh via API

### Admin Portal
- Same as web clients
- Additional MFA enforcement

## Response Format

### Standard Response
```json
{
  "success": true,
  "data": {...},
  "message": "Operation successful",
  "errors": []
}
```

### Error Response
```json
{
  "success": false,
  "data": null,
  "message": "Error description",
  "errors": ["field: error detail"]
}
```

### Paginated Response
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

## Permission Vocabulary

### Backend Permissions
Fine-grained permission codes:
- `rescue:create`
- `medical:clearance`
- `adoption:approve`

### Client Aliases
Coarse-grained aliases for UI gating:
- `rescue:write` (rescue:create/update/delete)
- `donations:write` (donation:manage/update)
- `complaints:write` (grievance:*)
- `notifications:write` (notification:manage)

## Real-Time Features

### WebSocket (Future)
- Dispatch updates
- Notification delivery
- Agent location tracking

### Server-Sent Events (Current)
- Redis Pub/Sub for dispatch events
- Polling for notifications

## Mobile-Specific Features

### Push Notifications
- Firebase Cloud Messaging (FCM)
- Device token registration
- Topic-based subscriptions

### Offline Support
- Local data caching
- Sync when online
- Conflict resolution

### Device Tracking
- Device ID, name, type
- Session management per device

## Web-Specific Features

### CORS Configuration
```python
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,https://pawguard-web.vercel.app
```

### Cookie Configuration
```python
COOKIE_DOMAIN=localhost
COOKIE_SECURE=false  # true in production
```

## Rate Limiting by Client

All clients share rate limits:
- Authenticated: Limited by user ID
- Anonymous: Limited by IP address

## API Documentation

### OpenAPI Schema
- Available at `/docs` (Swagger UI)
- Available at `/redoc` (ReDoc)
- Available at `/openapi.json` (JSON)
- Only in non-production environments

### Postman Collection
- `Pawguard.postman_collection.json`
- Complete API coverage
- Environment variables for configuration

## Cross-Platform Testing

### Unit Tests
- Service logic tested independently
- No client-specific code

### Integration Tests
- API endpoints tested with multiple client types
- Authentication tested for each client

### E2E Tests
- Complete workflows per client
- Mobile-specific flows (push notifications)
- Web-specific flows (cookie handling)

## Deployment by Client

### Public Website
- Vercel deployment
- Static site generation
- CDN for assets

### Admin Portal
- Vercel deployment
- Same as public website

### Mobile Apps
- App Store / Play Store
- Backend API integration
- Push notification setup

### Backend
- Render / Docker
- Single deployment serves all clients
