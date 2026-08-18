# External Integrations

Scope: Firebase Cloud Messaging, S3/Supabase storage, email delivery, payment gateway, OAuth providers, and integration patterns.

---

## 1. Integration Overview

| Integration | Purpose | Protocol | Library |
|------------|---------|----------|---------|
| Firebase Cloud Messaging | Push notifications | HTTPS | `firebase-admin >= 6.5.0` |
| AWS S3 / Supabase Storage | Object storage | HTTPS (presigned) | `boto3 >= 1.35.0` |
| Brevo API / SMTP | Email delivery | HTTPS / SMTP | `urllib` / `smtplib` |
| Razorpay | Payment processing | HTTPS | `razorpay >= 2.0.0` |
| Google OAuth | Social login | HTTPS | `httpx` |
| Apple OAuth | Social login | HTTPS | `pyjwt` |

All integrations follow the same principles:
1. Lazy initialization (connect only when needed)
2. Graceful degradation (never crash the API)
3. Structured logging (every call logged)
4. Timeout enforcement (no blocking calls)

---

## 2. Firebase Cloud Messaging (FCM)

### Purpose

Send push notifications to mobile devices (Rescue Staff App, Executive App).

### Architecture

```
NotificationService
    |
    v
PushService (services/push_service.py)
    |
    v
Firebase Admin SDK (firebase_admin)
    |
    v
FCM API (https://fcm.googleapis.com/v1/projects/...)
    |
    v
Device (iOS / Android)
```

### Initialization

Firebase is lazy-initialized on first push attempt:

```python
def _get_firebase_app() -> Any:
    global _firebase_initialized, _firebase_app
    if _firebase_initialized:
        return _firebase_app
    
    settings = get_settings()
    if not fcm_credentials_path and not fcm_credentials_json:
        logger.debug("fcm_not_configured")
        _firebase_initialized = True
        return None
    
    try:
        import firebase_admin
        from firebase_admin import credentials
        
        if fcm_credentials_json:
            cred = credentials.Certificate(json.loads(fcm_credentials_json))
        else:
            cred = credentials.Certificate(fcm_credentials_path)
        
        _firebase_app = firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        return _firebase_app
    except Exception as exc:
        logger.warning("fcm_init_failed", error=str(exc))
        _firebase_initialized = True
        return None
```

### Configuration

| Variable | Purpose |
|----------|---------|
| `FCM_CREDENTIALS_PATH` | Path to Firebase service account JSON file |
| `FCM_CREDENTIALS_JSON` | Raw JSON string of Firebase credentials (alternative) |

When both are unset, push notifications silently degrade to in-app only.

### Single Device Push

```python
async def send_push_notification(
    fcm_token: str,
    *,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    user_id: uuid.UUID | None = None,
) -> bool:
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        token=fcm_token,
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default", badge=1)
            )
        ),
    )
    response = await asyncio.to_thread(messaging.send, message, app=app)
    return True
```

### Multi-Device Push

```python
async def send_push_notification_to_users(
    user_tokens: list[tuple[uuid.UUID, str]],
    *,
    title: str,
    body: str,
    max_concurrency: int = 10,
) -> int:
    sem = asyncio.Semaphore(max_concurrency)
    results = await asyncio.gather(
        *[_send_one(uid, tok) for uid, tok in valid_tokens],
        return_exceptions=True,
    )
    return sum(1 for r in results if r is True)
```

### Safety Properties

- **Never raises** - Push failures are logged and return `False`
- **Concurrency limited** - Semaphore prevents FCM rate limiting
- **Lazy init** - Firebase SDK initialized only when needed
- **Graceful absent** - When unconfigured, returns `False` silently

Source: `src/pawguard/services/push_service.py:1-132`

---

## 3. Object Storage (S3 / Supabase)

### Purpose

Store and retrieve media files (dog photos, adoption images, documents) via presigned URLs.

### Architecture

```
StorageService (services/storage_service.py)
    |
    v
boto3 S3 Client (path-style addressing)
    |
    v
S3-Compatible Storage (AWS S3 / Supabase Storage)
    |
    v
Presigned URLs (direct client upload/download)
```

### Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `S3_BUCKET_NAME` | `pawguard-media` | Bucket name |
| `S3_REGION` | `us-east-1` | AWS region |
| `S3_ENDPOINT_URL` | (empty) | Custom endpoint (Supabase) |
| `AWS_ACCESS_KEY_ID` | `testing_access_key` | Access credentials |
| `AWS_SECRET_ACCESS_KEY` | `testing_secret_key` | Secret credentials |

### Path-Style Addressing

Supabase Storage requires path-style addressing (not virtual-hosted-style):

```python
self._client = boto3.client(
    "s3",
    region_name=settings.s3_region or "ap-southeast-1",
    endpoint_url=settings.s3_endpoint_url or None,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
```

### Presigned Upload URL

```python
def generate_presigned_upload_url(
    self, *, object_key: str, content_type: str, expires_in: int = 900
) -> str:
    url = self._client.generate_presigned_url(
        "put_object",
        Params={"Bucket": self._bucket, "Key": object_key},
        ExpiresIn=expires_in,
    )
    return url
```

**Design decision:** `Content-Type` is intentionally NOT part of the signed headers. Many client HTTP stacks (Flutter, mobile webviews) omit or rewrite this header, causing 403 errors. Real content validation happens in `confirm_upload` (magic bytes + size).

### Presigned Download URL

```python
def generate_presigned_download_url(
    self, *, object_key: str, expires_in: int = 900
) -> str:
    url = self._client.generate_presigned_url(
        "get_object",
        Params={"Bucket": self._bucket, "Key": object_key},
        ExpiresIn=expires_in,
    )
    return url
```

### Object Operations

| Method | Purpose |
|--------|---------|
| `build_object_key(folder, filename)` | Generate unique object key with UUID |
| `get_object_size(object_key)` | Get object size via HEAD request |
| `get_object_prefix_bytes(object_key, num_bytes)` | Read first N bytes (magic byte detection) |
| `get_object(object_key)` | Download full object |
| `put_object(object_key, content, content_type)` | Upload object directly |
| `delete_object(object_key)` | Delete object |

### Error Handling

```python
class StorageError(AppException):
    status_code = 503
    code = "STORAGE_UNAVAILABLE"
```

Storage errors raise `StorageError` (503) instead of returning broken URLs. This ensures clients get a clear error rather than a 403 "permission denied" from S3.

Source: `src/pawguard/services/storage_service.py:1-136`

---

## 4. Email Delivery

### Architecture

```
EmailService (services/email_service.py)
    |
    +--- Brevo HTTP API (preferred, port 443)
    |         |
    |         v
    |    Brevo SMTP Relay
    |
    +--- SMTP Fallback (port 587)
              |
              v
         SMTP Server
```

### Delivery Strategy

1. **Brevo HTTP API** (preferred) - Works on all cloud platforms, including Render free tier where outbound SMTP ports (587/465) may be blocked
2. **SMTP Fallback** - Used when no Brevo API key is configured

### Configuration

| Variable | Purpose |
|----------|---------|
| `BREVO_API_KEY` | Brevo REST API key (xkeysib-...) |
| `MAIL_FROM` | Sender address |
| `MAIL_HOST` | SMTP host (fallback) |
| `MAIL_PORT` | SMTP port (fallback) |
| `MAIL_USERNAME` | SMTP username |
| `MAIL_PASSWORD` | SMTP password |
| `MAIL_USE_TLS` | Enable STARTTLS |
| `MAIL_USE_SSL` | Enable SSL/TLS |

### Brevo API Delivery

```python
def _send_via_brevo_api(self, *, to: str, subject: str, html_body: str) -> None:
    payload = json.dumps({
        "sender": {"name": "PawGuard", "email": self._settings.mail_from_email},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html_body,
    }).encode()
    
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "api-key": self._settings.brevo_api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        status = resp.status
```

### Template Rendering

Emails use Jinja2 templates from `src/pawguard/templates/email/`:

| Template | Purpose |
|----------|---------|
| `password_reset.html` | Password reset link |
| `email_verification.html` | Email verification link |
| `notification.html` | General notification |

```python
_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

def render(self, template_name: str, context: dict[str, object]) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(**context)
```

### Transaction Rule Compliance

Email delivery is only ever invoked from ARQ background jobs, never inline within HTTP requests or database transactions.

Source: `src/pawguard/services/email_service.py:1-134`

---

## 5. Payment Gateway

### Provider-Agnostic Design

The payment system uses an abstract `PaymentGateway` interface:

```python
class PaymentGateway(ABC):
    provider_name: str
    
    @abstractmethod
    async def create_order(
        self, *, amount: float, currency: str, receipt: str, notes: dict[str, str] | None
    ) -> PaymentOrder:
        """Create payment intent with provider."""
    
    @abstractmethod
    def verify_payment_signature(
        self, *, order_id: str, payment_id: str, signature: str
    ) -> PaymentVerificationResult:
        """Verify provider's checkout callback signature."""
    
    @abstractmethod
    def parse_webhook(self, *, payload: bytes, signature: str) -> WebhookEvent:
        """Parse and verify webhook signature."""
```

### Current Implementation: Razorpay

```python
# From core/payments/razorpay_gateway.py
class RazorpayGateway(PaymentGateway):
    provider_name = "razorpay"
    
    async def create_order(self, *, amount, currency, receipt, notes=None) -> PaymentOrder:
        # Razorpay API call
        ...
    
    def verify_payment_signature(self, *, order_id, payment_id, signature) -> PaymentVerificationResult:
        # HMAC-SHA256 signature verification
        ...
    
    def parse_webhook(self, *, payload, signature) -> WebhookEvent:
        # Webhook signature verification
        ...
```

### Configuration

| Variable | Purpose |
|----------|---------|
| `PAYMENT_PROVIDER` | Provider name (default: `razorpay`) |
| `PAYMENT_CURRENCY` | Default currency (default: `INR`) |
| `RAZORPAY_KEY_ID` | Razorpay API key |
| `RAZORPAY_KEY_SECRET` | Razorpay API secret |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook signature secret |

### Data Models

```python
@dataclass(frozen=True)
class PaymentOrder:
    provider: str
    order_id: str
    amount: float
    currency: str
    checkout_key: str
    receipt: str

@dataclass(frozen=True)
class PaymentVerificationResult:
    verified: bool
    payment_id: str | None = None
    order_id: str | None = None
    failure_reason: str | None = None

@dataclass(frozen=True)
class WebhookEvent:
    event_type: str
    order_id: str | None
    payment_id: str | None
    is_success: bool
    raw_payload: dict[str, object]
```

### Swapping Providers

To add a new payment provider:
1. Implement `PaymentGateway` interface
2. Register in `core/payments/__init__.py`
3. Flip `PAYMENT_PROVIDER` config value
4. No changes to services, routers, or schemas

Source: `src/pawguard/core/payments/base.py:1-65`

---

## 6. OAuth Providers

### Supported Providers

| Provider | Client ID Config | Verification Endpoint |
|----------|-----------------|----------------------|
| Google | `GOOGLE_OAUTH_CLIENT_ID` | `https://oauth2.googleapis.com/tokeninfo` |
| Apple | `APPLE_OAUTH_CLIENT_ID` | `https://appleid.apple.com/auth/keys` |

### Google OAuth Flow

```python
async with httpx.AsyncClient() as client:
    resp = await client.get(
        f"https://oauth2.googleapis.com/tokeninfo?id_token={token}",
        timeout=10,
    )
    data = resp.json()
    
    # Verify audience (client ID)
    if data.get("aud") != expected_aud:
        raise InvalidCredentialsError("Google token was not issued for this application.")
    
    # Verify email is verified
    if not data.get("email_verified"):
        raise InvalidCredentialsError("Google email not verified.")
    
    return {
        "sub": data["sub"],
        "email": data.get("email", ""),
        "name": data.get("name", ""),
        "picture": data.get("picture", ""),
    }
```

### Apple OAuth Flow

```python
# Fetch Apple public keys
resp = await client.get("https://appleid.apple.com/auth/keys", timeout=10)
keys = resp.json()["keys"]

# Match key by kid header
header = pyjwt.get_unverified_header(token)
matching_key = next((k for k in keys if k["kid"] == header.get("kid")), None)

# Verify token with public key
public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(matching_key)
payload = pyjwt.decode(
    token,
    public_key,
    algorithms=["RS256"],
    audience=expected_aud,
    options={"verify_aud": True},
)
```

### Security Properties

- **Audience verification** - Tokens must be issued for PawGuard's client ID
- **Email verification** - Unverified emails are rejected
- **Key rotation** - Apple public keys are fetched fresh on each verification
- **Provider isolation** - Unknown providers raise `InvalidCredentialsError`

Source: `src/pawguard/modules/auth/service.py:826-909`

---

## 7. Integration Patterns

### Lazy Initialization

All external clients are initialized on first use, not at import time:

```python
_firebase_initialized = False
_firebase_app = None

def _get_firebase_app() -> Any:
    global _firebase_initialized, _firebase_app
    if _firebase_initialized:
        return _firebase_app
    # ... initialize on first call
```

### Graceful Degradation

| Integration | Behavior When Unavailable |
|------------|--------------------------|
| FCM | Returns `False`, push skipped |
| S3 | Raises `StorageError` (503) |
| Brevo/SMTP | Raises delivery exception (retryable) |
| Razorpay | Returns `None`, donation created without payment |
| Google/Apple OAuth | Raises `InvalidCredentialsError` (401) |
| Redis | `_NullRedis` no-ops, API continues |

### Timeout Enforcement

| Integration | Timeout |
|------------|---------|
| Brevo API | 15 seconds |
| SMTP | 10 seconds |
| Google OAuth | 10 seconds |
| Apple OAuth | 10 seconds |
| Firebase | Wrapped in `asyncio.to_thread()` (non-blocking) |

### Structured Logging

Every integration call is logged with relevant context:

```python
logger.info("email_sent", to=to, subject=subject, method="brevo_api", status=status)
logger.warning("fcm_init_failed", error=str(exc))
logger.error("brevo_api_error", to=to, subject=subject, status=exc.code, body=body)
logger.debug("push_sent", message_id=response, user_id=str(user_id))
```

---

## 8. Environment Variables Reference

### FCM Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `FCM_CREDENTIALS_PATH` | No | Path to Firebase service account JSON |
| `FCM_CREDENTIALS_JSON` | No | Raw JSON string of Firebase credentials |

### S3 Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `S3_BUCKET_NAME` | No | `pawguard-media` | S3 bucket name |
| `S3_REGION` | No | `us-east-1` | AWS region |
| `S3_ENDPOINT_URL` | No | (empty) | Custom S3 endpoint (Supabase) |
| `AWS_ACCESS_KEY_ID` | No | `testing_access_key` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | No | `testing_secret_key` | AWS secret key |

### Email Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `BREVO_API_KEY` | No | Brevo HTTP API key (preferred) |
| `MAIL_FROM` | No | Sender address (default: `no-reply@pawguard.org`) |
| `MAIL_HOST` | No | SMTP host (fallback) |
| `MAIL_PORT` | No | SMTP port (default: 1025) |
| `MAIL_USERNAME` | No | SMTP username |
| `MAIL_PASSWORD` | No | SMTP password |
| `MAIL_USE_TLS` | No | Enable STARTTLS |
| `MAIL_USE_SSL` | No | Enable SSL/TLS |

### Payment Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PAYMENT_PROVIDER` | No | `razorpay` | Payment provider name |
| `PAYMENT_CURRENCY` | No | `INR` | Default currency |
| `RAZORPAY_KEY_ID` | No | (empty) | Razorpay API key |
| `RAZORPAY_KEY_SECRET` | No | (empty) | Razorpay API secret |
| `RAZORPAY_WEBHOOK_SECRET` | No | (empty) | Webhook signature secret |

### OAuth Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_OAUTH_CLIENT_ID` | No | Google OAuth client ID |
| `APPLE_OAUTH_CLIENT_ID` | No | Apple OAuth client ID |
