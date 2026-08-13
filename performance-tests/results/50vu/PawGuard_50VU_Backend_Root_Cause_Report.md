# PawGuard 50-VU Backend Root-Cause Analysis Report

## Issue Details

### Issue ID: PERF-50VU-001
- **Role**: Owner
- **Module**: Auth
- **Endpoint**: `POST /api/v1/auth/login`
- **HTTP Method**: `POST`
- **Expected Status**: `200 OK`
- **Actual Runtime Status**: `429 Too Many Requests`
- **Baseline Result**: `200 OK` (1 VU)
- **Load Result (50 VUs)**: `429 Too Many Requests`
- **Technical Classification**: `Rate Limit`
- **Root Cause Confidence**: **Confirmed**
- **Evidence**: `src/pawguard/modules/auth/router.py:67` defines `login_rate_limiter = rate_limit("login", 10, 60)`.
- **Backend Remediation**: Maintain security rate limits; instruct clients to cache and reuse JWT bearer tokens.

### Issue ID: PERF-50VU-002
- **Role**: Vet Clinic / Admin
- **Module**: Medical / Admin
- **Endpoints**: `/api/v1/medical/exams`, `/api/v1/admin/users`
- **HTTP Method**: `GET`
- **Expected Status**: `200 OK`
- **Actual Runtime Status**: `401 / 403`
- **Technical Classification**: `Authorization`
- **Root Cause Confidence**: **Confirmed**
- **Evidence**: `require_permission("admin:read")` guard in `src/pawguard/modules/auth/rbac.py`.
- **Backend Remediation**: Ensure test suite seeds admin and vet clinic user roles prior to load testing.
