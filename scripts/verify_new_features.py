import urllib.request
import urllib.parse
import json
import ssl
import uuid

BASE = "https://pawguard-backend-mqri.onrender.com"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

results = []
auth_token = None
my_user_id = None
dog_id = None
rescue_id = None
facility_id = None
section_id = None
kennel_id = None


def req(method, path, body=None, token=None, content_type="application/json"):
    url = BASE + path
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Origin", "https://pawguard-frontend.example.com")
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


def skip(name):
    print(f"  [SKIP] {name}")
    results.append(("SKIP", name))


# ============================================================
#  LOGIN
# ============================================================
print("=" * 70)
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
    print(f"  WARN: Skipping remaining tests -- no token")

# ============================================================
#  GET USER PROFILE
# ============================================================
print("\n" + "=" * 70)
print("GET USER PROFILE")

if auth_token:
    status, body, raw = req("GET", "/api/v1/auth/me", token=auth_token)
    test("GET /auth/me returns 200", status == 200)
    my_user_id = body.get("data", {}).get("id", body.get("id", None)) if isinstance(body, dict) else None
    print(f"  my_user_id: {my_user_id}")
    test("User ID obtained from /auth/me", bool(my_user_id))
else:
    skip("Skipped -- no auth token")

# ============================================================
#  FEATURE 1: ASSIGN COORDINATOR
# ============================================================
print("\n" + "=" * 70)
print("FEATURE 1: ASSIGN COORDINATOR")

if auth_token:
    # Create a dog
    print("\n-- Step 1: Create Dog --")
    status, body, raw = req("POST", "/api/v1/dogs", {
        "name": "CoordVerifyDog",
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

    # Create rescue report
    print("\n-- Step 2: Create Rescue Report --")
    status, body, raw = req("POST", "/api/v1/rescue/report", {
        "reporter_name": "TestCoordinator",
        "reporter_phone": "+1-555-1001",
        "location_address": "Test Verification St",
        "physical_condition": "fractured_injured",
        "severity": "high"
    }, token=auth_token)
    test("Rescue report returns 201 or 200", status in (200, 201))
    if isinstance(body, dict):
        rescue_id = body.get("data", {}).get("id", body.get("id", None))
        if not rescue_id:
            rescue_id = body.get("ticket_number", None)
            # If still no id, try first item if it's a list
            if not rescue_id and isinstance(body.get("data"), list):
                rescue_id = body["data"][0].get("id", None) if body["data"] else None
    print(f"  rescue_id: {rescue_id}")
    test("Rescue ID obtained from report response", bool(rescue_id))

    # Assign coordinator
    if rescue_id and my_user_id:
        print(f"\n-- Step 3: Assign Coordinator --")
        status, body, raw = req("POST", f"/api/v1/rescue/{rescue_id}/assign-coordinator", {
            "coordinator_id": my_user_id,
            "notes": "Live verification test"
        }, token=auth_token)
        test("Assign coordinator returns 200", status == 200)
        test("Response includes coordinator_id", isinstance(body, dict) and "coordinator_id" in str(body))
        if status == 200 and isinstance(body, dict):
            data = body.get("data", {}) if isinstance(body.get("data"), dict) else {}
            coord_id = data.get("coordinator_id", data.get("coordinated_by"))
            print(f"  response coordinator_id: {coord_id}")
    else:
        skip("Skipped assign-coordinator -- missing rescue_id or user_id")
else:
    skip("Skipped all -- no auth token")

# ============================================================
#  FEATURE 2: NOTIFICATIONS WITH TARGET_ROLES
# ============================================================
print("\n" + "=" * 70)
print("FEATURE 2: NOTIFICATIONS WITH TARGET_ROLES")

if auth_token:
    print("\n-- Send notification with target_roles --")
    status, body, raw = req("POST", "/api/v1/notifications/send", {
        "title": "Target Role Test",
        "body": "Live verification of target_roles feature.",
        "notification_type": "test",
        "target_roles": ["general_public"]
    }, token=auth_token)
    test("Send with target_roles returns 201", status == 201)
    if status == 201 or status == 200:
        data = body.get("data", {}) if isinstance(body, dict) else {}
        if isinstance(data, list):
            test("Response contains list of notifications", len(data) > 0)
            print(f"  notifications sent: {len(data)}")
        else:
            test("Response contains notification data", bool(data))
    else:
        print(f"  RESPONSE: {raw[:500]}")
else:
    skip("Skipped -- no auth token")

# ============================================================
#  FEATURE 3: SHELTER SANITATION (MissingGreenlet fix check)
# ============================================================
print("\n" + "=" * 70)
print("FEATURE 3: SHELTER SANITATION (MissingGreenlet fix)")

if auth_token:
    # Create facility
    print("\n-- Step 1: Create Facility --")
    status, body, raw = req("POST", "/api/v1/shelter/facilities", {
        "name": "SanitationVerifyFacility",
        "address": "888 Test Ave",
        "phone": "+1-555-2001",
        "total_capacity": 20,
        "facility_type": "shelter"
    }, token=auth_token)
    test("Create facility returns 201", status == 201)
    if isinstance(body, dict):
        facility_id = body.get("data", {}).get("id", body.get("id", None))
    print(f"  facility_id: {facility_id}")
    test("Facility ID obtained", bool(facility_id))

    # Create section
    if facility_id:
        print("\n-- Step 2: Create Section --")
        status, body, raw = req("POST", f"/api/v1/shelter/facilities/{facility_id}/sections", {
            "name": "SanitationSection",
            "section_type": "general",
            "capacity": 10
        }, token=auth_token)
        test("Create section returns 201", status == 201)
        if isinstance(body, dict):
            section_id = body.get("data", {}).get("id", body.get("id", None))
        print(f"  section_id: {section_id}")
        test("Section ID obtained", bool(section_id))
    else:
        section_id = None
        skip("Skipped section creation -- no facility")

    # Create kennel
    if section_id:
        print("\n-- Step 3: Create Kennel --")
        status, body, raw = req("POST", f"/api/v1/shelter/sections/{section_id}/kennels", {
            "identifier": "K-SAN-01",
            "capacity": 1
        }, token=auth_token)
        test("Create kennel returns 201", status == 201)
        if isinstance(body, dict):
            kennel_id = body.get("data", {}).get("id", body.get("id", None))
        print(f"  kennel_id: {kennel_id}")
        test("Kennel ID obtained", bool(kennel_id))
    else:
        kennel_id = None
        skip("Skipped kennel creation -- no section")

    # Update sanitation (the MissingGreenlet bug check)
    if kennel_id:
        print(f"\n-- Step 4: Update Sanitation (kennel_id={kennel_id}) --")
        status, body, raw = req("PUT", f"/api/v1/shelter/kennels/{kennel_id}/sanitation?status_val=needs_cleaning", token=auth_token)
        test("Sanitation update returns 200 (was 422 bug)", status == 200)
        if status != 200:
            print(f"  FULL RESPONSE: {raw[:800]}")
    else:
        skip("Skipped sanitation update -- no kennel")
else:
    skip("Skipped all -- no auth token")

# ============================================================
#  SUMMARY
# ============================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
for result, name in results:
    print(f"  [{result}] {name}")

pass_count = sum(1 for r, _ in results if r == "PASS")
fail_count = sum(1 for r, _ in results if r == "FAIL")
skip_count = sum(1 for r, _ in results if r == "SKIP")
print(f"\n  TOTAL: {len(results)} tests | PASS: {pass_count} | FAIL: {fail_count} | SKIP: {skip_count}")
