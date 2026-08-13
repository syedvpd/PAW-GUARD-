# PawGuard 50-VU Load Test Audit Report

**Test Run ID**: `K6_50VU_20260813_122600`  
**Target Environment**: `https://pawguard-backend-mqri.onrender.com`  
**Concurrency**: `50 Concurrent VUs` (Owner: 30, Vet Clinic: 12, Admin: 8)  
**Execution Timestamp**: `2026-08-13 12:40:12`  
**Overall Evaluation**: **FAIL**

---

## 1. Executive Performance Summary

During the 4-minute 50-VU concurrent load test against the PawGuard backend:
- **Total Requests Executed**: `2,129`
- **Sustained Throughput**: `8.67 RPS`
- **HTTP Failure Rate**: `35.74%`
- **Check Pass Rate**: `85.63%`
- **p95 Response Latency**: `8892.93 ms`
- **p99 Response Latency**: `0.00 ms`

---

## 2. Threshold & SLA Audit Findings

### Observation PERF-50VU-001: Auth Login Endpoint Rate Limiting (HTTP 429)
- **Role**: Owner / All Roles
- **Endpoint**: `POST /api/v1/auth/login`
- **Requirement / SLA**: `< 1.0% failure rate`
- **Evidence**: `POST /api/v1/auth/login` returns HTTP 429 when hit at concurrency due to `login_rate_limiter = rate_limit("login", 10, 60)`.
- **Actual Result**: `HTTP 429 Too Many Requests` when requests exceed 10 logins/minute.
- **Technical Classification**: `Rate Limit`
- **Root Cause**: **Confirmed** — Rate limiter middleware enforcing 10 logins/60 seconds per IP.
- **Impact**: Dynamic multi-user re-authentication under high concurrency triggers security throttling.
- **Remediation Recommendation**: In production, clients reuse long-lived JWT access tokens and refresh tokens rather than issuing repeated login credentials per request.

### Observation PERF-50VU-002: Role Permission Guards (HTTP 401/403)
- **Role**: Vet Clinic & Admin
- **Endpoints**: `/api/v1/medical/exams`, `/api/v1/admin/users`
- **Requirement / SLA**: `< 1.0% failure rate`
- **Evidence**: Accounts registered dynamically without explicit database promotion default to `general_public` role.
- **Actual Result**: Role permission dependencies (`require_permission("admin:read")`) correctly reject unauthorized tokens.
- **Technical Classification**: `Authorization`
- **Root Cause**: **Confirmed** — RBAC permission guards enforce authorization controls.
- **Impact**: Security controls function as designed, rejecting unauthorized role access.

---

## 3. Post-Fix Verification Plan

1. Developers inspect rate limits and token lifecycle settings.
2. Execute the identical 50-VU k6 scenario on `feat/companion-pet-medical-endpoints`.
3. Verify failure rate drops below 1.0%.
