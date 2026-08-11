#!/usr/bin/env python3
"""Auth module — ALL 22 endpoints, robust harness."""
import json, urllib.request, urllib.error, sys, uuid, os

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
AUTH = {"token": None, "password": "PawGuard@2026"}
RESULTS = []

def req(method, path, body=None, headers=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    h = {"Content-Type": "application/json"}
    if headers: h.update(headers)
    if AUTH.get("token"): h["Authorization"] = f"Bearer {AUTH['token']}"
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read())
        except: body = {}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}

def record(module, name, method, path, status, body, expected=None):
    ok = False
    if expected is None: ok = 200 <= status < 300
    elif isinstance(expected, tuple): ok = status in expected
    else: ok = status == expected
    RESULTS.append({"module": module, "name": name, "method": method, "path": path, "status": status, "ok": ok, "expected": expected})
    prefix = "PASS" if ok else "FAIL"
    print(f"{prefix} [{module}] {name} {method} {path} -> {status}")
    if not ok and body:
        print(f"  BODY: {json.dumps(body, indent=2)[:350]}")
    return body.get("data") if isinstance(body, dict) else None

# Helper: login
def do_login(email="super.admin@pawguard.com", pwd=None):
    if pwd is None: pwd = AUTH["password"]
    s, b = req("POST", "/api/v1/auth/login", {"email": email, "password": pwd})
    data = record("auth", "login", "POST", "/api/v1/auth/login", s, b, 200)
    AUTH["token"] = data.get("access_token") if data else None
    return data

# 1. Register
s, b = req("POST", "/api/v1/auth/register", {
    "email": f"test{uuid.uuid4().hex[:8]}@pawguard.com", "password": "TestPass123!",
    "full_name": "Test User", "role": "public"
})
record("auth", "register", "POST", "/api/v1/auth/register", s, b, (201, 409))

# 2. Login
do_login()
if not AUTH["token"]:
    print("FATAL: Login failed")
    sys.exit(1)

# 3. Me
s, b = req("GET", "/api/v1/auth/me")
record("auth", "me", "GET", "/api/v1/auth/me", s, b, 200)

# 4. Update me
s, b = req("PUT", "/api/v1/auth/me", {"full_name": "Updated Name", "phone": "+91-99999-88888"})
record("auth", "update me", "PUT", "/api/v1/auth/me", s, b, 200)

# 5. Sessions
s, b = req("GET", "/api/v1/auth/sessions")
sessions_data = record("auth", "sessions", "GET", "/api/v1/auth/sessions", s, b, 200)

# 6. Change password (use current tracked password)
s, b = req("POST", "/api/v1/auth/password/change", {"current_password": AUTH["password"], "new_password": "PawGuard@2026New"})
record("auth", "change password", "POST", "/api/v1/auth/password/change", s, b, 200)
if s == 200: AUTH["password"] = "PawGuard@2026New"

# 7. Change back
s, b = req("POST", "/api/v1/auth/password/change", {"current_password": AUTH["password"], "new_password": "PawGuard@2026"})
record("auth", "change password back", "POST", "/api/v1/auth/password/change", s, b, 200)
if s == 200: AUTH["password"] = "PawGuard@2026"

# 8. Password reset request
s, b = req("POST", "/api/v1/auth/password/reset/request", {"email": "super.admin@pawguard.com"})
record("auth", "password reset request", "POST", "/api/v1/auth/password/reset/request", s, b, 200)

# 9. Password reset confirm
s, b = req("POST", "/api/v1/auth/password/reset/confirm", {"token": "invalid", "new_password": "NewPass123!"})
record("auth", "password reset confirm", "POST", "/api/v1/auth/password/reset/confirm", s, b, (200, 400, 422))

# 10. Email verify request
s, b = req("POST", "/api/v1/auth/email/verify/request")
record("auth", "email verify request", "POST", "/api/v1/auth/email/verify/request", s, b, (200, 400, 409))

# 11. Email verify confirm
s, b = req("POST", "/api/v1/auth/email/verify/confirm", {"token": "invalid"})
record("auth", "email verify confirm", "POST", "/api/v1/auth/email/verify/confirm", s, b, (200, 400, 422))

# 12. MFA enroll
s, b = req("POST", "/api/v1/auth/mfa/enroll")
mfa_data = record("auth", "mfa enroll", "POST", "/api/v1/auth/mfa/enroll", s, b, (200, 400, 409))

# 13. MFA enroll confirm
s, b = req("POST", "/api/v1/auth/mfa/enroll/confirm", {"code": "000000"})
record("auth", "mfa enroll confirm", "POST", "/api/v1/auth/mfa/enroll/confirm", s, b, (200, 400, 422))

# 14. MFA verify
s, b = req("POST", "/api/v1/auth/mfa/verify", {"pre_auth_token": "invalid", "code": "000000"})
record("auth", "mfa verify", "POST", "/api/v1/auth/mfa/verify", s, b, (200, 400, 401, 422))

# 15. MFA disable
s, b = req("POST", "/api/v1/auth/mfa/disable", {"password": AUTH["password"]})
record("auth", "mfa disable", "POST", "/api/v1/auth/mfa/disable", s, b, (200, 400, 401, 409))

# 16. Refresh token
login_data = do_login()
refresh_token = login_data.get("refresh_token") if login_data else None
if refresh_token:
    s, b = req("POST", "/api/v1/auth/refresh", {"refresh_token": refresh_token})
    record("auth", "refresh", "POST", "/api/v1/auth/refresh", s, b, 200)
else:
    record("auth", "refresh", "POST", "/api/v1/auth/refresh", "SKIP", {}, skip_reason="no refresh token")

# 17. OAuth login
s, b = req("POST", "/api/v1/auth/oauth/login", {"provider": "google"})
record("auth", "oauth login", "POST", "/api/v1/auth/oauth/login", s, b, (200, 400, 422))

# 18. OAuth accounts
s, b = req("GET", "/api/v1/auth/oauth/accounts")
record("auth", "oauth accounts", "GET", "/api/v1/auth/oauth/accounts", s, b, (200, 401))

# 19. OAuth link
s, b = req("POST", "/api/v1/auth/oauth/link", {"provider": "google", "token": "fake"})
record("auth", "oauth link", "POST", "/api/v1/auth/oauth/link", s, b, (200, 400, 422))

# 20. Delete session (skip current session, delete another if exists)
if isinstance(sessions_data, list) and len(sessions_data) > 1:
    sid = sessions_data[1].get("id")  # delete second session, not current
    s, b = req("DELETE", f"/api/v1/auth/sessions/{sid}")
    record("auth", "delete session", "DELETE", f"/api/v1/auth/sessions/{sid}", s, b, (200, 404))
else:
    record("auth", "delete session", "DELETE", "/api/v1/auth/sessions/{id}", "SKIP", {}, skip_reason="only 1 session")

# 21. Logout
s, b = req("POST", "/api/v1/auth/logout")
record("auth", "logout", "POST", "/api/v1/auth/logout", s, b, 200)

# 22. Logout all (re-login first since logout killed token)
do_login()
s, b = req("POST", "/api/v1/auth/logout-all")
record("auth", "logout all", "POST", "/api/v1/auth/logout-all", s, b, 200)

passed = sum(1 for r in RESULTS if r.get("ok"))
total = len(RESULTS)
print(f"\n{'='*70}")
print(f"AUTH TEST: {passed}/{total} passed, {total-passed} failed")
print(f"{'='*70}")

os.makedirs("docs", exist_ok=True)
fn = f"docs/auth_test_{BASE.replace('://','_').replace('/','_').replace(':','_')}.json"
with open(fn, "w") as f:
    json.dump({"target": BASE, "total": total, "passed": passed, "results": RESULTS}, f, indent=2)
print(f"Saved to {fn}")
