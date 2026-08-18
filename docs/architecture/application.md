# Application Layer Architecture

Scope: Module structure, service/repository pattern, dependency injection, and middleware design.

---

## 1. Module Architecture

The application is organized into 27 domain modules under `src/pawguard/modules/`. Each module encapsulates a complete business domain with consistent internal structure.

### Module Inventory

| Module | Router Prefix | Domain |
|--------|--------------|--------|
| `auth` | `/auth` | Authentication, authorization, MFA, OAuth, sessions |
| `admin` | `/admin` | Admin dashboard, audit logs |
| `adoption` | `/adoption` | Adoption applications, processing |
| `companion_pet` | `/companion-pet`, `/veterinary` | Pet registration, safety tags, vet appointments |
| `dashboards` | `/dashboards` | Dashboard aggregations |
| `dog` | `/dogs` | Dog profiles, weight logs, QR scans, safety tags |
| `donation` | `/donations` | Donations, sponsorships, recurring payments |
| `finance` | `/finance` | Financial reconciliation, reports |
| `fleet` | `/fleet` | Vehicle fleet management |
| `foster` | `/foster` | Foster home management |
| `grievance` | `/grievance` | Grievance tickets, SLA, feedback surveys |
| `inventory` | `/inventory` | Inventory items, low stock, expiry |
| `lost_found` | `/lost-found` | Lost pet alerts, found reports |
| `medical` | `/medical` | Medical records, vaccinations |
| `notifications` | `/notifications` | In-app, email, push notifications |
| `outbox` | (internal) | Transactional outbox for background jobs |
| `portal` | `/portal` | Portal stats, content |
| `reports` | `/reports` | Report generation |
| `rescue` | `/rescue` | Rescue case management |
| `rescue_centre` | `/rescue-centre` | Rescue centre facilities |
| `settings` | `/settings` | System settings |
| `shelter` | `/shelter` | Shelter facility management |
| `storage` | `/storage` | File upload/download |
| `volunteer` | `/volunteer` | Volunteer management |

### Standard Module Structure

Every domain module follows this internal layout:

```
modules/<module_name>/
    __init__.py
    models.py          # SQLAlchemy ORM models
    schemas.py         # Pydantic request/response schemas
    repository.py      # Database access (queries only)
    service.py         # Business logic (RULE-003)
    router.py          # API endpoints (RULE-004)
    README.md          # Module documentation (optional)
```

Some modules include additional files:
- `exceptions.py` - Module-specific exception classes
- `audit.py` - Audit service factory
- `admin_router.py` - Admin-specific endpoints

---

## 2. Layer Responsibilities

The architecture enforces strict layer separation per AGENTS.md RULE-001 through RULE-004.

### Router Layer (API Endpoints)

**Source pattern:** `modules/*/router.py`

Routers are responsible for exactly four things:

1. **Authenticate** - Extract and validate JWT via `get_current_user` dependency
2. **Authorize** - Check permissions via `require_permission` dependency
3. **Validate** - Pydantic model validation (automatic via FastAPI)
4. **Call Service** - Delegate to the appropriate service method
5. **Return Response** - Wrap result in `ApiResponse` or `PaginatedResponse`

```python
# Typical router pattern (from modules/dog/router.py)
@router.post(
    "",
    response_model=ApiResponse[DogProfileResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("shelter:update"))],
)
async def register_dog(
    payload: DogProfileCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: DogService = Depends(get_dog_service),
) -> ApiResponse[DogProfileResponse]:
    dog = await service.register_dog(
        payload,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
    )
    return ApiResponse(
        data=DogProfileResponse.model_validate(dog),
        message="Dog profile registered successfully.",
    )
```

**Forbidden patterns in routers:**
- Direct database queries
- Business logic decisions
- Conditional validation rules
- Session management

Source: `src/pawguard/modules/dog/router.py:90-110`

### Service Layer (Business Logic)

**Source pattern:** `modules/*/service.py`

Services own all business behavior. They:

- Enforce business rules and invariants
- Coordinate multiple repository calls
- Manage transaction boundaries
- Emit audit log entries
- Interface with shared services (cache, email, push)

```python
# Typical service constructor (from modules/auth/service.py)
class AuthService:
    def __init__(
        self,
        *,
        user_repo: UserRepository,
        session_repo: SessionRepository,
        refresh_token_repo: RefreshTokenRepository,
        mfa_repo: MFARepository,
        password_reset_repo: PasswordResetTokenRepository,
        email_verification_repo: EmailVerificationTokenRepository,
        oauth_account_repo: OAuthAccountRepository,
        audit_service: AuditService,
    ) -> None:
        self._users = user_repo
        self._sessions = session_repo
        self._refresh_tokens = refresh_token_repo
        self._mfa = mfa_repo
        self._password_resets = password_reset_repo
        self._email_verifications = email_verification_repo
        self._oauth_accounts = oauth_account_repo
        self._audit = audit_service
        self._settings = get_settings()
```

Services receive repositories and shared services via constructor injection, never importing them directly.

Source: `src/pawguard/modules/auth/service.py:105-126`

### Repository Layer (Data Access)

**Source pattern:** `modules/*/repository.py`

Repositories are responsible for:

- Translating business queries into SQLAlchemy statements
- Executing queries within the provided session
- Returning ORM model instances

**Forbidden in repositories:**
- Business logic decisions
- Permission checks
- Transaction commit/rollback (managed by service or session dependency)
- Cross-module queries

---

## 3. Dependency Injection

FastAPI's dependency injection system is used extensively to wire components together.

### Session Injection

```python
# From db/session.py
async def get_db(request: Request = None) -> AsyncGenerator[AsyncSession]:
    if request is not None and request.method == "GET":
        async with AsyncReplicaSessionLocal() as session:
            # Read requests use replica
            ...
    else:
        async with AsyncSessionLocal() as session:
            # Write requests use primary
            ...
```

GET requests are automatically routed to the read replica. All other methods use the primary database.

Source: `src/pawguard/db/session.py:121-141`

### Service Factory Pattern

Each router defines a factory function that wires its service with the correct dependencies:

```python
# From modules/dog/router.py
def get_dog_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    redis: RedisClient = Depends(get_redis),
) -> DogService:
    return DogService(DogRepository(db), audit_service=audit, redis=redis)
```

This pattern ensures:
- Each request gets a fresh service instance
- Dependencies are resolved automatically
- Testing is straightforward via dependency overrides

Source: `src/pawguard/modules/dog/router.py:60-65`

### Authentication Dependencies

| Dependency | Source | Purpose |
|-----------|--------|---------|
| `get_current_user` | `modules/auth/dependencies.py` | Requires valid JWT, returns `CurrentUser` |
| `get_optional_current_user` | `modules/auth/dependencies.py` | Returns `CurrentUser` or `None` |
| `require_permission(code)` | `modules/auth/rbac.py` | Requires specific permission code |
| `is_admin_role(claims)` | `modules/auth/rbac.py` | Checks for super_admin role |
| `has_permission(user, code)` | `modules/auth/rbac.py` | Direct permission check on User object |

Source: `src/pawguard/modules/auth/rbac.py:55-84`

---

## 4. Response Envelope

Every API response follows a standardized envelope format defined in `core/responses.py`:

### Success Response

```json
{
    "success": true,
    "data": { ... },
    "message": "Optional human-readable message"
}
```

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

### Error Response

```json
{
    "success": false,
    "error": {
        "code": "VALIDATION_FAILED",
        "message": "Validation failed for 'body.email': value is not a valid email",
        "details": [...]
    }
}
```

Source: `src/pawguard/core/responses.py:1-35`

---

## 5. Pagination and Sorting

### Pagination

Standardized via `core/pagination.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `page` | 1 | Page number (1-indexed) |
| `page_size` | 20 | Items per page |

### Sorting

Standardized via `core/search.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `sort_by` | `created_at` | Field to sort by |
| `sort_order` | `desc` | Direction: `asc` or `desc` |

### Search

Free-text search is module-specific but follows a consistent pattern via the `search` query parameter.

---

## 6. Rate Limiting

Per-endpoint rate limiting is implemented via Redis-backed sliding window counters.

```python
# Usage in router
@router.post("/login")
async def login(_: Annotated[None, Depends(rate_limit("login", max_requests=10, window_seconds=60))]):
    ...
```

### Rate Limit Configuration

| Endpoint | Max Requests | Window |
|----------|-------------|--------|
| Login | 10 | 60 seconds |
| Refresh | 30 | 60 seconds |
| Password Reset | 5 | 3600 seconds |
| Dog Public Scan | 20 | 60 seconds |

### Client Identification

Rate limits are keyed by:
1. Authenticated `user_id` (when available)
2. Client IP address (fallback)

IP resolution respects `CF-Connecting-IP` (Cloudflare) and `X-Forwarded-For` (rightmost entry).

Source: `src/pawguard/core/rate_limiter.py:1-72`

---

## 7. Idempotency

Mutating requests (POST, PUT, PATCH, DELETE) can include an `Idempotency-Key` or `X-Idempotency-Key` header for deduplication.

### Behavior

1. Key must be 10-128 characters
2. Key is bound to the authenticated user session
3. Request payload hash is computed and stored
4. Duplicate requests with different payloads return 400
5. In-flight requests return 409
6. Completed responses are cached for 24 hours
7. 5xx responses are never cached

### Cache Header

Responses include `X-Cache-Idempotency: HIT` or `MISS`.

Source: `src/pawguard/core/idempotency.py:40-180`

---

## 8. RBAC Permission System

### Permission Model

```
User -> Role (many-to-many) -> Permission (many-to-many)
```

### Admin Bypass

Only `super_admin` and `system:admin` roles bypass all permission checks. Every other role (including `rescue_centre_admin`, `admin`) must have explicit permissions.

### Permission Caching

Permission lookups are cached in Redis under the `rbac` namespace:
- Key: `rbac:roles:{sorted_role_names}`
- TTL: 300 seconds
- Cache is invalidated on any role mutation

Source: `src/pawguard/modules/auth/rbac.py:12-84`

---

## 9. Audit Trail

Every significant state change is recorded in `auth_audit_logs` via `AuditService`.

### Audit Event Types

| Category | Events |
|----------|--------|
| Authentication | `LOGIN_SUCCESS`, `LOGIN_FAILED`, `LOGOUT`, `LOGOUT_ALL` |
| Registration | `REGISTERED`, `EMAIL_VERIFIED` |
| Password | `PASSWORD_RESET_REQUESTED`, `PASSWORD_RESET_COMPLETED`, `PASSWORD_CHANGE` |
| MFA | `MFA_ENROLLED`, `MFA_VERIFIED`, `MFA_FAILED`, `MFA_DISABLED` |
| Sessions | `SESSION_REVOKED` |
| OAuth | `OAUTH_LOGIN`, `OAUTH_LINKED`, `OAUTH_UNLINKED` |
| Admin | `ADMIN_USER_CREATED`, `ADMIN_USER_UPDATED`, `ADMIN_USER_DELETED` |
| Token | `REFRESH`, `REFRESH_REUSE_DETECTED` |
| Profile | `PROFILE_UPDATED` |

### Audit Record Structure

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | UUID | Actor performing the action |
| `event_type` | String | Event category |
| `ip_address` | String | Client IP address |
| `user_agent` | String | Client user agent |
| `event_metadata` | JSONB | Additional context |
| `before_state` | JSONB | State before change |
| `after_state` | JSONB | State after change |

Source: `src/pawguard/services/audit_service.py:37-66`

---

## 10. Shared Services

Common functionality is extracted into reusable services under `src/pawguard/services/`:

| Service | Source | Purpose |
|---------|--------|---------|
| `CacheService` | `services/cache_service.py` | Redis operations with namespace isolation |
| `EmailService` | `services/email_service.py` | Jinja2 rendering + delivery (Brevo/SMTP) |
| `PushService` | `services/push_service.py` | FCM push notifications |
| `StorageService` | `services/storage_service.py` | S3 presigned URLs, object CRUD |
| `AuditService` | `services/audit_service.py` | Audit log writer |

These services are injected into module services via constructor dependencies, never imported directly in routers.

---

## 11. Exception Hierarchy

Module-specific exceptions extend the base `AppException`:

```
AppException
    +-- NotFoundError
    +-- ValidationFailedError
    +-- ConflictError
    +-- UnauthorizedError
    +-- ForbiddenError
    +-- TooManyRequestsError
    +-- StorageError
    +-- PaymentGatewayError
    +-- InvalidCredentialsError (auth)
    +-- AccountLockedError (auth)
    +-- AccountInactiveError (auth)
    +-- MFAAlreadyEnabledError (auth)
    +-- InvalidMFACodeError (auth)
    +-- RefreshTokenReuseDetectedError (auth)
    +-- InsufficientPermissionsError (auth)
```

Every exception carries:
- `status_code` - HTTP status code
- `code` - Machine-readable error code
- `message` - Client-safe error message

Source: `src/pawguard/core/exceptions.py:23-63`
