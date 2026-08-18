# Authentication API

## Overview

The authentication module handles user registration, login, MFA, OAuth social login, session management, password reset, and email verification. All endpoints follow the standard response envelope.

**Prefix:** `/api/v1/auth`

---

## Endpoints

### Register

**`POST /auth/register`**

Creates a new user account and sends a verification email.

**Rate Limit:** 5 requests per hour

**Request Body:**

```json
{
  "email": "jane.doe@example.com",
  "password": "StrongP@ssw0rd",
  "full_name": "Jane Doe",
  "phone": "+919876543210"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email` | string | Yes | Valid email format |
| `password` | string | Yes | Min 10 chars, uppercase, lowercase, digit |
| `full_name` | string | Yes | Alpha characters, spaces, hyphens, apostrophes only |
| `phone` | string | No | E.164 format (e.g., `+919876543210`) |

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "jane.doe@example.com",
    "full_name": "Jane Doe",
    "phone": "+919876543210",
    "is_verified": false,
    "mfa_enabled": false,
    "roles": ["public"]
  },
  "message": "Registration successful. Please verify your email."
}
```

---

### Login

**`POST /auth/login`**

Authenticates a user and returns access/refresh tokens. If MFA is enabled, returns a `pre_auth_token` instead.

**Rate Limit:** 10 requests per minute

**Request Body:**

```json
{
  "email": "jane.doe@example.com",
  "password": "StrongP@ssw0rd",
  "device": {
    "device_id": "a1b2c3d4-device-001",
    "device_name": "Jane's iPhone 15",
    "device_type": "ios"
  }
}
```

**Response (without MFA):**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "dGhpc2lzYXJlZnJlc2h0b2tlbg==",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "jane.doe@example.com",
      "full_name": "Jane Doe",
      "roles": ["public"]
    }
  }
}
```

**Response (MFA required):**

```json
{
  "success": true,
  "data": {
    "mfa_required": true,
    "pre_auth_token": "a1b2c3d4e5f6-pre-auth"
  }
}
```

**Web Client Behavior:** When the `X-Client-Type: web` header is present, tokens are set as HttpOnly cookies and `refresh_token` is omitted from the response body.

---

### Verify MFA Login

**`POST /auth/mfa/verify`**

Completes the login flow when MFA is enabled.

**Rate Limit:** 10 requests per 5 minutes

**Request Body:**

```json
{
  "pre_auth_token": "a1b2c3d4e5f6-pre-auth",
  "code": "482913",
  "device": {
    "device_id": "a1b2c3d4-device-001",
    "device_name": "Jane's iPhone 15",
    "device_type": "ios"
  }
}
```

**Response:** Same as Login response.

---

### Refresh Token

**`POST /auth/refresh`**

Exchanges a refresh token for a new access token.

**Rate Limit:** 30 requests per minute

**Request Body:**

```json
{
  "refresh_token": "dGhpc2lzYXJlZnJlc2h0b2tlbg=="
}
```

If `refresh_token` is omitted, the endpoint reads from the `refresh_token` cookie (web clients).

**Response:**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "dGhpc2lzYXJlZnJlc2h0b2tlbg==",
    "token_type": "bearer",
    "expires_in": 3600
  }
}
```

---

### Logout

**`POST /auth/logout`**

Terminates the current session and clears auth cookies (web clients).

**Authentication:** Required

**Response:**

```json
{
  "success": true,
  "message": "Logged out."
}
```

---

### Logout All Sessions

**`POST /auth/logout-all`**

Terminates all sessions except the current one.

**Authentication:** Required

**Response:**

```json
{
  "success": true,
  "message": "Logged out from all devices."
}
```

---

### Get Current User

**`GET /auth/me`**

Returns the authenticated user's profile.

**Authentication:** Required

**Response:**

```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "jane.doe@example.com",
    "full_name": "Jane Doe",
    "phone": "+919876543210",
    "profile_picture_url": "https://example.com/avatar.jpg",
    "date_of_birth": "1995-05-15",
    "gender": "female",
    "address_line": "123 Rescue Way",
    "city": "Sector 4",
    "state": "Telangana",
    "country": "India",
    "postal_code": "500081",
    "push_notifications_enabled": true,
    "is_verified": true,
    "mfa_enabled": false,
    "roles": ["rescue_agent"]
  }
}
```

---

### Update Profile

**`PUT /auth/me`**

Updates the authenticated user's profile. At least one field must be provided.

**Authentication:** Required

**Request Body:**

```json
{
  "full_name": "Jane Smith",
  "phone": "+1-555-0100",
  "avatar_url": "https://example.com/new-avatar.jpg",
  "dob": "1995-05-15",
  "gender": "female",
  "address": "123 Rescue Way",
  "city": "Sector 4",
  "state": "Telangana",
  "country": "India",
  "pin_code": "500081",
  "push_notifications": true
}
```

**Response:** Updated `UserProfile` object.

---

### List Sessions

**`GET /auth/sessions`**

Returns all active sessions for the authenticated user.

**Authentication:** Required

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": "session-uuid-1",
      "device_name": "Jane's iPhone 15",
      "device_type": "ios",
      "ip_address": "192.168.1.100",
      "is_active": true,
      "last_used_at": "2026-08-18T10:30:00Z",
      "created_at": "2026-08-17T08:00:00Z",
      "is_current": true
    }
  ],
  "message": "Active sessions retrieved successfully."
}
```

---

### Revoke Session

**`DELETE /auth/sessions/{session_id}`**

Terminates a specific session.

**Authentication:** Required

**Response:**

```json
{
  "success": true,
  "message": "Session revoked."
}
```

---

### Change Password

**`POST /auth/password/change`**

Changes the authenticated user's password. All other sessions are logged out.

**Rate Limit:** 10 requests per 5 minutes

**Request Body:**

```json
{
  "current_password": "OldP@ssw0rd",
  "new_password": "NewStr0ng!Pass"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Password changed. Other sessions have been logged out."
}
```

---

### Request Password Reset

**`POST /auth/password/reset/request`**

Sends a password reset email to the specified address.

**Rate Limit:** 5 requests per hour

**Request Body:**

```json
{
  "email": "jane.doe@example.com"
}
```

**Response:**

```json
{
  "success": true,
  "message": "If that email exists, a reset link has been sent."
}
```

---

### Confirm Password Reset

**`POST /auth/password/reset/confirm`**

Resets the password using the token from the email.

**Rate Limit:** 10 requests per 5 minutes

**Request Body:**

```json
{
  "token": "a1b2c3d4e5f6-reset-token",
  "new_password": "NewStr0ng!Pass"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Password has been reset."
}
```

---

### Verify Email

**`POST /auth/email/verify/confirm`**

Confirms email verification using the token from the email.

**Rate Limit:** 10 requests per 5 minutes

**Request Body:**

```json
{
  "token": "a1b2c3d4e5f6-verify-token"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Email verified."
}
```

---

### Request Email Verification

**`POST /auth/email/verify/request`**

Sends a new verification email to the authenticated user.

**Rate Limit:** 10 requests per 5 minutes

**Authentication:** Required

**Response:**

```json
{
  "success": true,
  "message": "Verification email sent."
}
```

---

### Enroll MFA

**`POST /auth/mfa/enroll`**

Initiates MFA enrollment by generating a TOTP secret and provisioning URI.

**Authentication:** Required

**Response:**

```json
{
  "success": true,
  "data": {
    "secret": "JBSWY3DPEHPK3PXP",
    "provisioning_uri": "otpauth://totp/PawGuard:jane@example.com?secret=JBSWY3DPEHPK3PXP&issuer=PawGuard"
  }
}
```

---

### Confirm MFA Enrollment

**`POST /auth/mfa/enroll/confirm`**

Completes MFA enrollment by verifying a TOTP code.

**Rate Limit:** 10 requests per 5 minutes

**Request Body:**

```json
{
  "code": "482913"
}
```

**Response:**

```json
{
  "success": true,
  "message": "MFA enabled."
}
```

---

### Disable MFA

**`POST /auth/mfa/disable`**

Disables MFA. Requires either the current password or a valid TOTP code.

**Rate Limit:** 10 requests per 5 minutes

**Request Body:**

```json
{
  "password": "CurrentP@ssw0rd",
  "totp_code": "482913"
}
```

**Response:**

```json
{
  "success": true,
  "message": "MFA disabled."
}
```

---

### OAuth Login

**`POST /auth/oauth/login`**

Authenticates via a social provider (Google, etc.).

**Rate Limit:** 10 requests per minute

**Request Body:**

```json
{
  "provider": "google",
  "provider_token": "ya29.a0AfH6SMC...token",
  "device": {
    "device_id": "a1b2c3d4-device-001",
    "device_name": "Jane's iPhone 15",
    "device_type": "ios"
  }
}
```

**Response:** Same as Login response.

---

### List OAuth Accounts

**`GET /auth/oauth/accounts`**

Returns linked OAuth accounts for the authenticated user.

**Authentication:** Required

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": "account-uuid",
      "provider": "google",
      "provider_user_id": "123456789",
      "provider_email": "jane@gmail.com",
      "display_name": "Jane Doe",
      "picture_url": "https://lh3.googleusercontent.com/...",
      "created_at": "2026-08-17T08:00:00Z"
    }
  ]
}
```

---

### Link OAuth Account

**`POST /auth/oauth/link`**

Links a social provider account to the authenticated user.

**Authentication:** Required

**Request Body:**

```json
{
  "provider": "google",
  "provider_token": "ya29.a0AfH6SMC...token"
}
```

**Response:** `OAuthAccountInfo` object.

---

### Unlink OAuth Account

**`DELETE /auth/oauth/accounts/{account_id}`**

Removes a linked OAuth account.

**Authentication:** Required

**Response:**

```json
{
  "success": true,
  "message": "OAuth account unlinked."
}
```
