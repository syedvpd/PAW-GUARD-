# PawGuard 50-VU Backend Remediation Guide

## Remediation Item 1: Token Reuse Architecture
- **Affected File**: `src/pawguard/modules/auth/router.py`
- **Current Behavior**: Enforces 10 logins per 60 seconds per IP.
- **Recommended Backend Action**: Retain rate limiting for security against brute-force attacks. Mobile/Web client applications should store the access token in memory or secure storage and use `/api/v1/auth/refresh` when expired.

## Remediation Item 2: Pre-Seeding Test Credentials for Load Testing
- **Affected Module**: `scripts/seed_scale_data.py`
- **Current Behavior**: New users registered during test runs hold `general_public` role.
- **Recommended Backend Action**: Use pre-seeded Admin and Vet Clinic test tokens when executing synthetic performance benchmarks.
