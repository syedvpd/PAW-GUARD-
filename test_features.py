import urllib.request
import urllib.parse
import json
import ssl

BASE = "http://127.0.0.1:8000"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

results = []
auth_token = None
my_user_id = None
dog_id = None
rescue_id = None


def req(method, path, body=None, token=None, content_type="application/json"):
    url = BASE + path
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Origin", "http://localhost")
    if content_type:
        r.add_header("Content-Type", content_type)
    if token:
        r.add_header("Authorization", f"Bearer {token}")

    print(f"  {method} {path}")
    try:
        resp = urllib.request.urlopen(r, context=ctx)
        raw = resp.read().decode("utf-8")
        status = resp.status
        try:
            body_resp = json.loads(raw)
        except Exception:
            body_resp = raw
        print(f"  -> {status}")
        return status, body_resp, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            body_resp = json.loads(raw)
        except Exception:
            body_resp = raw
        print(f"  -> {e.code}")
        print(f"  BODY: {raw[:500]}")
        return e.code, body_resp, raw
    except Exception as e:
        print(f"  -> ERROR: {e}")
        return None, str(e), str(e)


def test(name, condition):
    if condition:
        print(f"  [PASS] {name}")
        results.append(("PASS", name))
    else:
        print(f"  [FAIL] {name}")
        results.append(("FAIL", name))


def auth_header():
    global auth_token
    return auth_token


# ============================================================
#  LOGIN
# ============================================================
print("=" * 60)
print("LOGIN")
status, body, raw = req("POST", "/api/v1/auth/login", {
    "email": "super.admin@pawguard.com",
    "password": "PawGuard@2026"
})
test("Login returns 200", status == 200)
if status == 200:
    auth_token = body.get("data", {}).get("access_token", body.get("access_token", None))
    test("Auth token obtained", bool(auth_token))
else:
    auth_token = None
    print(f"  WARN: Skipping remaining tests — no token")

# ============================================================
#  FEATURE 1: ASSIGN COORDINATOR
# ============================================================
print("\n" + "=" * 60)
print("FEATURE 1: ASSIGN COORDINATOR")

if auth_token:
    # Step: Create a dog
    print("\n-- Create Dog --")
    status, body, raw = req("POST", "/api/v1/dogs", {
        "name": "CoordDog",
        "breed": "Indie",
        "gender": "male",
        "estimated_age": "1",
        "age_months": 12,
        "weight": 10,
        "color": "Brown",
        "is_adoptable": True
    }, token=auth_token)
    test("Create dog returns 201 or 200", status in (200, 201))
    dog_id = body.get("data", {}).get("id", body.get("id", None)) if isinstance(body, dict) else None
    print(f"  dog_id: {dog_id}")

    # Step: Get logged-in user profile
    print("\n-- Get My Profile --")
    status, body, raw = req("GET", "/api/v1/auth/me", token=auth_token)
    test("GET /auth/me returns 200", status == 200)
    my_user_id = body.get("data", {}).get("id", body.get("id", None)) if isinstance(body, dict) else None
    print(f"  my_user_id: {my_user_id}")
    test("User ID obtained from /auth/me", bool(my_user_id))

    # Step: Create rescue report
    print("\n-- Create Rescue Report --")
    status, body, raw = req("POST", "/api/v1/rescue/report", {
        "reporter_name": "TestCoord",
        "reporter_phone": "+1-555-0001",
        "location_address": "Test St",
        "physical_condition": "fractured_injured",
        "severity": "high"
    }, token=auth_token)
    test("Rescue report returns 201 or 200", status in (200, 201))
    if isinstance(body, dict):
        rescue_id = body.get("data", {}).get("id", body.get("id", None))
        if not rescue_id:
            # maybe nested differently
            rescue_id = body.get("rescue_id", body.get("request_id", None))
    print(f"  rescue_id: {rescue_id}")
    test("Rescue ID obtained from response", bool(rescue_id))

    # Step: Assign coordinator
    if rescue_id and my_user_id:
        print(f"\n-- Assign Coordinator (rescue_id={rescue_id}) --")
        status, body, raw = req("POST", f"/api/v1/rescue/{rescue_id}/assign-coordinator", {
            "coordinator_id": my_user_id,
            "notes": "Testing coordinator assignment"
        }, token=auth_token)
        test("Assign coordinator returns 200", status == 200)
        test("Response includes coordinator_id", isinstance(body, dict) and "coordinator_id" in str(body))
    else:
        test("Skipped assign-coordinator — missing rescue_id or user_id", False)
else:
    print("  SKIP: No auth token")

# ============================================================
#  FEATURE 2: NOTIFICATIONS WITH TARGET_ROLES
# ============================================================
print("\n" + "=" * 60)
print("FEATURE 2: NOTIFICATIONS WITH TARGET_ROLES")

if auth_token:
    # Test 1: Send with target_roles
    print("\n-- Send with target_roles --")
    status, body, raw = req("POST", "/api/v1/notifications/send", {
        "title": "Test Role Alert",
        "body": "This is a role-targeted notification.",
        "notification_type": "test",
        "target_roles": ["general_public"]
    }, token=auth_token)
    test("Send with target_roles returns 200", status == 200)
    if status != 200:
        print(f"  RESPONSE: {raw[:500]}")

    # Test 2: Send with user_id (backward compat)
    print("\n-- Send with user_id (backward compat) --")
    status, body, raw = req("POST", "/api/v1/notifications/send", {
        "user_id": my_user_id,
        "title": "Test Single",
        "body": "Single user notification",
        "notification_type": "test"
    }, token=auth_token)
    test("Send with user_id returns 200", status == 200)
    if status != 200:
        print(f"  RESPONSE: {raw[:500]}")

    # Test 3: Broadcast with target_roles
    print(f"\n-- Broadcast with target_roles (user_ids={my_user_id}) --")
    status, body, raw = req("POST", f"/api/v1/notifications/broadcast?user_ids={my_user_id}", {
        "title": "Broadcast Role",
        "body": "Broadcast to roles",
        "notification_type": "test",
        "target_roles": ["general_public"]
    }, token=auth_token)
    test("Broadcast with target_roles returns 200", status == 200)
    if status != 200:
        print(f"  RESPONSE: {raw[:500]}")
else:
    print("  SKIP: No auth token")
    test("Skipped all notification tests — no auth token", False)

# ============================================================
#  SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
for result, name in results:
    print(f"  [{result}] {name}")

pass_count = sum(1 for r, _ in results if r == "PASS")
fail_count = sum(1 for r, _ in results if r == "FAIL")
print(f"\n  TOTAL: {len(results)} tests | PASS: {pass_count} | FAIL: {fail_count}")
