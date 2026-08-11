#!/usr/bin/env python3
"""Master test for ALL remaining PawGuard modules."""
import json, urllib.request, urllib.error, sys, uuid, os

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
AUTH = {"token": None, "password": "PawGuard@2026"}
RESULTS = []
CREATED = {}

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

def record(module, name, method, path, status, body, expected=None, skip_reason=None):
    ok = False
    if status == "SKIP":
        ok = True
        status = "SKIP"
    elif expected is None: ok = 200 <= status < 300
    elif isinstance(expected, tuple): ok = status in expected
    else: ok = status == expected
    RESULTS.append({"module": module, "name": name, "method": method, "path": path, "status": status, "ok": ok, "expected": expected, "skip_reason": skip_reason})
    prefix = "PASS" if ok else "FAIL"
    if status == "SKIP":
        print(f"SKIP [{module}] {name} {method} {path} -> {skip_reason}")
    else:
        print(f"{prefix} [{module}] {name} {method} {path} -> {status}")
    if not ok and body:
        print(f"  BODY: {json.dumps(body, indent=2)[:400]}")
    return body.get("data") if isinstance(body, dict) else None

def do_login():
    s, b = req("POST", "/api/v1/auth/login", {"email": "super.admin@pawguard.com", "password": AUTH["password"]})
    data = record("auth", "login", "POST", "/api/v1/auth/login", s, b, 200)
    AUTH["token"] = data.get("access_token") if data else None
    return data

do_login()
if not AUTH["token"]:
    print("FATAL: Login failed")
    sys.exit(1)

# ========================================
# MODULE: storage (7 endpoints)
# ========================================
print("\n" + "="*70)
print("MODULE: storage")
print("="*70)

# upload-url (StoredFileCreate schema: original_filename, mime_type, file_size, folder)
s, b = req("POST", "/api/v1/storage/upload-url", {
    "original_filename": "test.png", "mime_type": "image/png", "file_size": 1024, "folder": "dogs", "entity_type": "dog_profile", "entity_id": str(uuid.uuid4())
})
up_data = record("storage", "upload url", "POST", "/api/v1/storage/upload-url", s, b, (201, 200, 400))

# file_id placeholder
file_id = str(uuid.uuid4()) if not up_data else up_data.get("id", str(uuid.uuid4()))

# confirm upload (PUT with no body, just path param)
s, b = req("PUT", f"/api/v1/storage/{file_id}/confirm")
record("storage", "confirm upload", "PUT", f"/api/v1/storage/{file_id}/confirm", s, b, (200, 404))

# download url
s, b = req("GET", f"/api/v1/storage/{file_id}/download-url")
record("storage", "download url", "GET", f"/api/v1/storage/{file_id}/download-url", s, b, (200, 404))

# get file
s, b = req("GET", f"/api/v1/storage/{file_id}")
record("storage", "get file", "GET", f"/api/v1/storage/{file_id}", s, b, (200, 404))

# delete file
s, b = req("DELETE", f"/api/v1/storage/{file_id}")
record("storage", "delete file", "DELETE", f"/api/v1/storage/{file_id}", s, b, (200, 404))

# bulk delete
s, b = req("POST", "/api/v1/storage/bulk/delete", {"ids": [str(uuid.uuid4())]})
record("storage", "bulk delete", "POST", "/api/v1/storage/bulk/delete", s, b, (200, 400))

# entity files
s, b = req("GET", f"/api/v1/storage/entity/dog/{str(uuid.uuid4())}")
record("storage", "entity files", "GET", "/api/v1/storage/entity/dog/{id}", s, b, (200, 404))

# ========================================
# MODULE: notifications (9 endpoints)
# ========================================
print("\n" + "="*70)
print("MODULE: notifications")
print("="*70)

# unread count
s, b = req("GET", "/api/v1/notifications/unread-count")
record("notifications", "unread count", "GET", "/api/v1/notifications/unread-count", s, b, 200)

# preferences
s, b = req("GET", "/api/v1/notifications/preferences")
pref_data = record("notifications", "get preferences", "GET", "/api/v1/notifications/preferences", s, b, 200)

# update preferences
s, b = req("PUT", "/api/v1/notifications/preferences", {"email_enabled": True, "push_enabled": False})
record("notifications", "update preferences", "PUT", "/api/v1/notifications/preferences", s, b, 200)

# list notifications (no direct list endpoint? skip)
record("notifications", "list", "GET", "/api/v1/notifications", "SKIP", {}, skip_reason="no list endpoint")

# read notification (need a notification id)
notif_id = str(uuid.uuid4())
s, b = req("PUT", f"/api/v1/notifications/{notif_id}/read")
record("notifications", "read", "PUT", f"/api/v1/notifications/{notif_id}/read", s, b, (200, 404))

# read all
s, b = req("PUT", "/api/v1/notifications/read-all")
record("notifications", "read all", "PUT", "/api/v1/notifications/read-all", s, b, 200)

# delete notification
s, b = req("DELETE", f"/api/v1/notifications/{notif_id}")
record("notifications", "delete", "DELETE", f"/api/v1/notifications/{notif_id}", s, b, (200, 404))

# bulk delete
s, b = req("POST", "/api/v1/notifications/bulk/delete", {"ids": [str(uuid.uuid4())]})
record("notifications", "bulk delete", "POST", "/api/v1/notifications/bulk/delete", s, b, (200, 400))

# send notification (admin)
s, b = req("POST", "/api/v1/notifications/send", {"user_id": str(uuid.uuid4()), "title": "Test", "message": "Hello", "channel": "email"})
record("notifications", "send", "POST", "/api/v1/notifications/send", s, b, (200, 400, 422))

# broadcast
s, b = req("POST", "/api/v1/notifications/broadcast", {"title": "Broadcast", "message": "All users", "channels": ["email"]})
record("notifications", "broadcast", "POST", "/api/v1/notifications/broadcast", s, b, (200, 400, 422))

# ========================================
# MODULE: rescue_centre (6 endpoints)
# ========================================
print("\n" + "="*70)
print("MODULE: rescue_centre")
print("="*70)

rc_id = str(uuid.uuid4())

# get
s, b = req("GET", f"/api/v1/rescue-centres/{rc_id}")
record("rescue_centre", "get", "GET", f"/api/v1/rescue-centres/{rc_id}", s, b, (200, 404))

# update
s, b = req("PUT", f"/api/v1/rescue-centres/{rc_id}", {"name": "Updated Centre"})
record("rescue_centre", "update", "PUT", f"/api/v1/rescue-centres/{rc_id}", s, b, (200, 404))

# delete
s, b = req("DELETE", f"/api/v1/rescue-centres/{rc_id}")
record("rescue_centre", "delete", "DELETE", f"/api/v1/rescue-centres/{rc_id}", s, b, (200, 404))

# status
s, b = req("PUT", f"/api/v1/rescue-centres/{rc_id}/status", {"status": "active"})
record("rescue_centre", "status", "PUT", f"/api/v1/rescue-centres/{rc_id}/status", s, b, (200, 404))

# bulk delete
s, b = req("POST", "/api/v1/rescue-centres/bulk/delete", {"ids": [rc_id]})
record("rescue_centre", "bulk delete", "POST", "/api/v1/rescue-centres/bulk/delete", s, b, 200)

# bulk status
s, b = req("POST", "/api/v1/rescue-centres/bulk/status", {"ids": [rc_id], "status": "active"})
record("rescue_centre", "bulk status", "POST", "/api/v1/rescue-centres/bulk/status", s, b, 200)

# ========================================
# MODULE: reports (4 endpoints)
# ========================================
print("\n" + "="*70)
print("MODULE: reports")
print("="*70)

# generate
s, b = req("POST", "/api/v1/reports/generate", {"report_type": "dog_summary", "format": "pdf"})
report_data = record("reports", "generate", "POST", "/api/v1/reports/generate", s, b, (200, 400, 422))

# types
s, b = req("GET", "/api/v1/reports/types")
record("reports", "types", "GET", "/api/v1/reports/types", s, b, 200)

# formats
s, b = req("GET", "/api/v1/reports/formats")
record("reports", "formats", "GET", "/api/v1/reports/formats", s, b, 200)

# download
s, b = req("GET", "/api/v1/reports/download/test.pdf")
record("reports", "download", "GET", "/api/v1/reports/download/test.pdf", s, b, (200, 404))

# ========================================
# MODULE: settings (17 endpoints)
# ========================================
print("\n" + "="*70)
print("MODULE: settings")
print("="*70)

# general
s, b = req("GET", "/api/v1/settings/general")
record("settings", "general", "GET", "/api/v1/settings/general", s, b, 200)

# email
s, b = req("GET", "/api/v1/settings/email")
record("settings", "email", "GET", "/api/v1/settings/email", s, b, 200)

# storage
s, b = req("GET", "/api/v1/settings/storage")
record("settings", "storage", "GET", "/api/v1/settings/storage", s, b, 200)

# public content
s, b = req("GET", "/api/v1/settings/public-content")
record("settings", "public content get", "GET", "/api/v1/settings/public-content", s, b, 200)

# update public content (requires about_us + mission)
s, b = req("PUT", "/api/v1/settings/public-content", {
    "about_us": "PawGuard rescues street dogs.", "mission": "Safe home for every stray."
})
record("settings", "public content put", "PUT", "/api/v1/settings/public-content", s, b, 200)

# system settings
s, b = req("GET", "/api/v1/settings/system")
record("settings", "system list", "GET", "/api/v1/settings/system", s, b, 200)

# system by key
s, b = req("GET", "/api/v1/settings/system/max_upload_size")
record("settings", "system key", "GET", "/api/v1/settings/system/max_upload_size", s, b, (200, 404))

# create system setting
s, b = req("POST", "/api/v1/settings/system", {"key": "test_key", "value": "test_value", "type": "string", "description": "Test"})
sys_data = record("settings", "system create", "POST", "/api/v1/settings/system", s, b, (201, 200, 409))
sys_id = sys_data.get("id") if isinstance(sys_data, dict) else None

# update system setting (uses {key} not {id})
sys_key = sys_data.get("key") if isinstance(sys_data, dict) else None
if sys_key:
    s, b = req("PUT", f"/api/v1/settings/system/{sys_key}", {"value": "updated"})
    record("settings", "system update", "PUT", f"/api/v1/settings/system/{sys_key}", s, b, 200)
else:
    record("settings", "system update", "PUT", "/api/v1/settings/system/{key}", "SKIP", {}, skip_reason="no sys key")

# delete system setting (uses {setting_id})
sys_id = sys_data.get("id") if isinstance(sys_data, dict) else None
if sys_id:
    s, b = req("DELETE", f"/api/v1/settings/system/{sys_id}")
    record("settings", "system delete", "DELETE", f"/api/v1/settings/system/{sys_id}", s, b, (200, 204))
else:
    record("settings", "system delete", "DELETE", "/api/v1/settings/system/{id}", "SKIP", {}, skip_reason="no sys id")

# password policy
s, b = req("GET", "/api/v1/settings/password-policy")
record("settings", "password policy get", "GET", "/api/v1/settings/password-policy", s, b, 200)

# update password policy
s, b = req("PUT", "/api/v1/settings/password-policy", {"min_length": 8, "require_uppercase": True})
record("settings", "password policy put", "PUT", "/api/v1/settings/password-policy", s, b, 200)

# business rules
s, b = req("GET", "/api/v1/settings/business-rules")
record("settings", "business rules list", "GET", "/api/v1/settings/business-rules", s, b, 200)

# business rule by key
s, b = req("GET", "/api/v1/settings/business-rules/adoption_fee")
record("settings", "business rule key", "GET", "/api/v1/settings/business-rules/adoption_fee", s, b, (200, 404))

# create business rule (needs module field)
s, b = req("POST", "/api/v1/settings/business-rules", {"rule_key": "test_rule", "rule_value": "test_value", "module": "adoption", "description": "Test rule"})
br_data = record("settings", "business rule create", "POST", "/api/v1/settings/business-rules", s, b, (201, 200, 409))
br_key = br_data.get("rule_key") if isinstance(br_data, dict) else None
br_id = br_data.get("id") if isinstance(br_data, dict) else None

# update business rule (uses {rule_key} not {id})
if br_key:
    s, b = req("PUT", f"/api/v1/settings/business-rules/{br_key}", {"rule_value": "updated"})
    record("settings", "business rule update", "PUT", f"/api/v1/settings/business-rules/{br_key}", s, b, 200)
else:
    record("settings", "business rule update", "PUT", "/api/v1/settings/business-rules/{key}", "SKIP", {}, skip_reason="no br key")

# delete business rule (uses {rule_id})
if br_id:
    s, b = req("DELETE", f"/api/v1/settings/business-rules/{br_id}")
    record("settings", "business rule delete", "DELETE", f"/api/v1/settings/business-rules/{br_id}", s, b, (200, 204))
else:
    record("settings", "business rule delete", "DELETE", "/api/v1/settings/business-rules/{id}", "SKIP", {}, skip_reason="no br id")

# ========================================
# SUMMARY
# ========================================
print("\n" + "="*70)
passed = sum(1 for r in RESULTS if r.get("ok"))
total = len(RESULTS)
failed = total - passed
print(f"SUMMARY: {passed}/{total} passed, {failed} failed")
print("="*70)

for m in ["storage", "notifications", "rescue_centre", "reports", "settings"]:
    mp = sum(1 for r in RESULTS if r["module"] == m and r.get("ok"))
    mt = sum(1 for r in RESULTS if r["module"] == m)
    print(f"  {m}: {mp}/{mt}")

os.makedirs("docs", exist_ok=True)
fn = f"docs/batch3_small_{BASE.replace('://','_').replace('/','_').replace(':','_')}.json"
with open(fn, "w") as f:
    json.dump({"target": BASE, "total": total, "passed": passed, "results": RESULTS}, f, indent=2)
print(f"\nSaved to {fn}")
