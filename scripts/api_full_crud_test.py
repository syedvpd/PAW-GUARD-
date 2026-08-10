"""Comprehensive CRUD test harness for PawGuard API.

Runs full CRUD flows (login -> GET all -> GET by id -> POST create -> PUT/PATCH -> DELETE)
against a base URL with real JSON bodies. Outputs structured JSON results.
"""
import json
import sys
import time
import uuid
import urllib.request
import urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
EMAIL = sys.argv[2] if len(sys.argv) > 2 else "super.admin@pawguard.com"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "PawGuard@2026"
TAG = uuid.uuid4().hex[:8]

RESULTS = []


def stamp():
    return f"{int(time.time())}-{TAG}"


def request(method, path, body=None, headers=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return "ERR", str(e)[:200]


def record(module, test, method, path, status, body, expect=200):
    ok = isinstance(status, int) and (
        expect is None
        or (isinstance(expect, tuple) and status in expect)
        or (isinstance(expect, int) and status == expect)
    )
    entry = {
        "module": module,
        "test": test,
        "method": method,
        "path": path,
        "status": status,
        "expected": expect,
        "ok": ok,
    }
    if isinstance(body, dict):
        entry["error"] = body.get("detail") or body.get("message") or ""
        if not ok and isinstance(body.get("detail"), list):
            entry["error"] = "; ".join(f"{e.get('loc','')}: {e.get('msg','')}" for e in body["detail"])
        if body.get("data") is not None and isinstance(body["data"], dict):
            entry["created_id"] = str(body["data"].get("id", ""))
    else:
        entry["error"] = str(body)[:200] if not ok else ""
    RESULTS.append(entry)
    print(f"{'PASS' if ok else 'FAIL'} [{module}] {test} -> {status}" + (f" | {entry['error'][:120]}" if not ok else ""))
    return entry


def login():
    status, body = request("POST", "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    if status != 200:
        print("LOGIN FAILED", status, json.dumps(body)[:300])
        sys.exit(1)
    token = body["data"].get("access_token") or body.get("access_token")
    print("LOGIN OK ->", EMAIL)
    return {"Authorization": f"Bearer {token}"}


def run_auth(headers):
    m = "auth"
    s, b = request("GET", "/api/v1/auth/me", headers=headers)
    record(m, "me", "GET", "/api/v1/auth/me", s, b)
    s, b = request("PUT", "/api/v1/auth/me", {"full_name": "Super Admin Demo"}, headers=headers)
    record(m, "update me", "PUT", "/api/v1/auth/me", s, b)
    s, b = request("GET", "/api/v1/auth/sessions", headers=headers)
    record(m, "sessions", "GET", "/api/v1/auth/sessions", s, b)


def run_dogs(headers):
    m = "dog"
    s, b = request("GET", "/api/v1/dogs?page=1&size=5", headers=headers)
    record(m, "list all", "GET", "/api/v1/dogs", s, b)
    dogs = b.get("data", []) if isinstance(b, dict) else []
    if dogs:
        did = dogs[0]["id"]
        s, b = request("GET", f"/api/v1/dogs/{did}", headers=headers)
        record(m, "get by id", "GET", f"/api/v1/dogs/{did}", s, b)
        s, b = request("GET", f"/api/v1/dogs/{did}/timeline", headers=headers)
        record(m, "timeline", "GET", f"/api/v1/dogs/{did}/timeline", s, b)
        s, b = request("GET", f"/api/v1/dogs/{did}/weights", headers=headers)
        record(m, "weights list", "GET", f"/api/v1/dogs/{did}/weights", s, b)
        s, b = request("PATCH", f"/api/v1/dogs/{did}/status", {"status": "shelter"}, headers=headers)
        record(m, "patch status", "PATCH", f"/api/v1/dogs/{did}/status", s, b)
    name = f"Demo Dog {stamp()}"
    body = {
        "name": name,
        "breed": "Indie Mix",
        "gender": "male",
        "estimated_age": "2 years",
        "age_months": 24,
        "weight": 16.4,
        "color": "Tan/White",
        "temperament": "friendly",
        "is_adoptable": False,
    }
    s, b = request("POST", "/api/v1/dogs", body, headers=headers)
    e = record(m, "create", "POST", "/api/v1/dogs", s, b, expect=201)
    created_id = e.get("created_id")
    if created_id:
        s, b = request("GET", f"/api/v1/dogs/{created_id}", headers=headers)
        record(m, "get created", "GET", f"/api/v1/dogs/{created_id}", s, b)
        s, b = request("PUT", f"/api/v1/dogs/{created_id}", {"name": name + " updated", "weight": 17.2}, headers=headers)
        record(m, "update", "PUT", f"/api/v1/dogs/{created_id}", s, b)
        s, b = request("POST", f"/api/v1/dogs/{created_id}/weight", {"weight": 17.2, "notes": "demo weigh-in"}, headers=headers)
        record(m, "record weight", "POST", f"/api/v1/dogs/{created_id}/weight", s, b, expect=201)
        s, b = request("DELETE", f"/api/v1/dogs/{created_id}", headers=headers)
        record(m, "delete", "DELETE", f"/api/v1/dogs/{created_id}", s, b)
        s, b = request("GET", f"/api/v1/dogs/{created_id}", headers=headers)
        record(m, "get after delete", "GET", f"/api/v1/dogs/{created_id}", s, b, expect=404)


def run_donations(headers):
    m = "donation"
    s, b = request("GET", "/api/v1/donations?page=1&page_size=5", headers=headers)
    record(m, "list all", "GET", "/api/v1/donations", s, b)
    donation_list = b.get("data", []) if isinstance(b, dict) else []
    s, b = request("GET", "/api/v1/donations/donors?page=1&page_size=5", headers=headers)
    record(m, "donors list", "GET", "/api/v1/donations/donors", s, b)
    s, b = request("GET", "/api/v1/donations/history", headers=headers)
    record(m, "history", "GET", "/api/v1/donations/history", s, b)
    s, b = request("GET", "/api/v1/donations/campaigns?page=1&page_size=5", headers=headers)
    record(m, "campaigns list", "GET", "/api/v1/donations/campaigns", s, b)
    if donation_list:
        did = donation_list[0]["id"]
        s, b = request("GET", f"/api/v1/donations/{did}/receipt", headers=headers)
        record(m, "receipt (404=no receipt yet)", "GET", f"/api/v1/donations/{did}/receipt", s, b, expect=(200, 404))
        s, b = request("POST", f"/api/v1/donations/{did}/reconcile", headers=headers)
        record(m, "reconcile info", "POST", f"/api/v1/donations/{did}/reconcile", s, b)
    s, b = request("POST", "/api/v1/donations/campaigns", {
        "name": f"Demo Campaign {stamp()}",
        "description": "Demo fundraising campaign",
        "target_amount": 5000.0,
        "currency": "INR",
        "campaign_type": "general",
        "status": "draft",
        "start_date": "2026-08-10",
        "end_date": "2026-09-30",
    }, headers=headers)
    e = record(m, "create campaign", "POST", "/api/v1/donations/campaigns", s, b, expect=201)
    cid = e.get("created_id")
    if cid:
        s, b = request("GET", f"/api/v1/donations/campaigns/{cid}", headers=headers)
        record(m, "get campaign", "GET", f"/api/v1/donations/campaigns/{cid}", s, b)
        s, b = request("PATCH", f"/api/v1/donations/campaigns/{cid}", {"description": "Updated demo campaign"}, headers=headers)
        record(m, "update campaign", "PATCH", f"/api/v1/donations/campaigns/{cid}", s, b)
        s, b = request("DELETE", f"/api/v1/donations/campaigns/{cid}", headers=headers)
        record(m, "delete campaign", "DELETE", f"/api/v1/donations/campaigns/{cid}", s, b)
    s, b = request("POST", "/api/v1/donations/register", {
        "amount": 100.0,
        "currency": "INR",
        "donation_type": "one_time",
        "notes": f"demo donation {stamp()}",
    }, headers=headers)
    record(m, "register donation", "POST", "/api/v1/donations/register", s, b, expect=201)


def run_grievance(headers):
    m = "grievance"
    s, b = request("POST", "/api/v1/grievance", {
        "reporter_name": "Demo Reporter",
        "reporter_phone": "+1-555-0199",
        "reporter_email": "demo@example.com",
        "complaint_type": "Rescue Delay",
        "details": f"Demo complaint created by test harness {stamp()}.",
    })
    e = record(m, "create (public)", "POST", "/api/v1/grievance", s, b, expect=201)
    tid = e.get("created_id")
    s, b = request("GET", "/api/v1/grievance?page=1&size=5", headers=headers)
    record(m, "list all", "GET", "/api/v1/grievance", s, b)
    if tid:
        s, b = request("GET", f"/api/v1/grievance/{tid}", headers=headers)
        record(m, "get by id", "GET", f"/api/v1/grievance/{tid}", s, b)
        s, b = request("PUT", f"/api/v1/grievance/{tid}", {"status": "investigating", "resolution_notes": "Reviewing dispatch records."}, headers=headers)
        record(m, "update", "PUT", f"/api/v1/grievance/{tid}", s, b)
        s, b = request("PATCH", f"/api/v1/grievance/{tid}/status?status=resolved", headers=headers)
        record(m, "patch status", "PATCH", f"/api/v1/grievance/{tid}/status", s, b)
        s, b = request("POST", f"/api/v1/grievance/{tid}/comments", {"body": "Follow-up comment from demo.", "is_internal": False}, headers=headers)
        record(m, "add comment", "POST", f"/api/v1/grievance/{tid}/comments", s, b, expect=201)
        s, b = request("GET", f"/api/v1/grievance/{tid}/comments", headers=headers)
        record(m, "list comments", "GET", f"/api/v1/grievance/{tid}/comments", s, b)
        s, b = request("DELETE", f"/api/v1/grievance/{tid}", headers=headers)
        record(m, "delete", "DELETE", f"/api/v1/grievance/{tid}", s, b)
    s, b = request("POST", "/api/v1/grievance/feedback", {"rating": 5, "comments": "Great service from demo harness."})
    record(m, "submit feedback (public)", "POST", "/api/v1/grievance/feedback", s, b, expect=201)


def run_lost_found(headers):
    m = "lost_found"
    s, b = request("GET", "/api/v1/lost-found/lost?page=1&size=5", headers=headers)
    record(m, "lost list", "GET", "/api/v1/lost-found/lost", s, b)
    s, b = request("GET", "/api/v1/lost-found/found?page=1&size=5", headers=headers)
    record(m, "found list", "GET", "/api/v1/lost-found/found", s, b)
    s, b = request("GET", "/api/v1/lost-found/reunion-stories", headers=headers)
    record(m, "reunion stories", "GET", "/api/v1/lost-found/reunion-stories", s, b)
    s, b = request("POST", "/api/v1/lost-found/lost", {
        "species": "dog",
        "pet_name": f"Buddy {stamp()}",
        "breed": "Beagle Mix",
        "color": "Tan/White",
        "collar_color": "Red",
        "location_address": "Jubilee Hills Sector 2",
        "latitude": 17.4326,
        "longitude": 78.4071,
        "lost_at": "2026-08-05T14:30:00Z",
        "photo_url": "https://example.com/buddy.jpg",
    }, headers=headers)
    e = record(m, "create lost report", "POST", "/api/v1/lost-found/lost", s, b, expect=201)
    lid = e.get("created_id")
    if lid:
        s, b = request("GET", f"/api/v1/lost-found/lost/{lid}", headers=headers)
        record(m, "get lost by id", "GET", f"/api/v1/lost-found/lost/{lid}", s, b)
        s, b = request("GET", f"/api/v1/lost-found/lost/{lid}/matches", headers=headers)
        record(m, "lost matches", "GET", f"/api/v1/lost-found/lost/{lid}/matches", s, b)
    s, b = request("POST", "/api/v1/lost-found/found", {
        "species": "dog",
        "breed_observed": "Beagle Mix",
        "color_observed": "Tan/White",
        "collar_color": "Red",
        "location_address": "Jubilee Hills Sector 3",
        "latitude": 17.4321,
        "longitude": 78.4055,
        "found_at": "2026-08-06T09:15:00Z",
        "photo_url": "https://example.com/found.jpg",
    }, headers=headers)
    e2 = record(m, "create found report", "POST", "/api/v1/lost-found/found", s, b, expect=201)
    fid = e2.get("created_id")
    if fid:
        s, b = request("GET", f"/api/v1/lost-found/found/{fid}", headers=headers)
        record(m, "get found by id", "GET", f"/api/v1/lost-found/found/{fid}", s, b)
        s, b = request("DELETE", f"/api/v1/lost-found/found/{fid}", headers=headers)
        record(m, "delete found", "DELETE", f"/api/v1/lost-found/found/{fid}", s, b)
    if lid:
        s, b = request("DELETE", f"/api/v1/lost-found/lost/{lid}", headers=headers)
        record(m, "delete lost", "DELETE", f"/api/v1/lost-found/lost/{lid}", s, b)


def run_volunteers(headers):
    m = "volunteer"
    s, b = request("GET", "/api/v1/volunteers?page=1&size=5", headers=headers)
    record(m, "list all", "GET", "/api/v1/volunteers", s, b)
    vols = b.get("data", []) if isinstance(b, dict) else []
    if vols:
        vid = vols[0]["id"]
        s, b = request("GET", f"/api/v1/volunteers/{vid}", headers=headers)
        record(m, "get by id", "GET", f"/api/v1/volunteers/{vid}", s, b)
        s, b = request("GET", f"/api/v1/volunteers/{vid}/service-summary", headers=headers)
        record(m, "service summary", "GET", f"/api/v1/volunteers/{vid}/service-summary", s, b)
        s, b = request("PUT", f"/api/v1/volunteers/{vid}", {"skills": "Grooming, Transport, First Aid", "availability": "Weekends"}, headers=headers)
        record(m, "update", "PUT", f"/api/v1/volunteers/{vid}", s, b)
    s, b = request("GET", "/api/v1/volunteers/shifts?page=1&page_size=5", headers=headers)
    record(m, "shifts list", "GET", "/api/v1/volunteers/shifts", s, b)
    s, b = request("POST", "/api/v1/volunteers/shifts", {
        "role_name": "Dog Walking",
        "start_at": "2026-08-20T09:00:00Z",
        "end_at": "2026-08-20T12:00:00Z",
        "capacity": 5,
    }, headers=headers)
    e = record(m, "create shift", "POST", "/api/v1/volunteers/shifts", s, b, expect=201)
    sid = e.get("created_id")


def main():
    headers = login()
    run_auth(headers)
    run_dogs(headers)
    run_donations(headers)
    run_grievance(headers)
    run_lost_found(headers)
    run_volunteers(headers)

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["ok"])
    failed = total - passed
    print("\n" + "=" * 70)
    print(f"TARGET: {BASE}")
    print(f"TOTAL: {total}  PASSED: {passed}  FAILED: {failed}")
    print("=" * 70)
    for r in RESULTS:
        if not r["ok"]:
            print(f"  FAIL {r['module']}:{r['test']} -> {r['status']} | {r.get('error','')[:150]}")
    with open(f"docs/api_test_report_{BASE.replace('://','_').replace('/','_')}.json", "w") as f:
        json.dump(RESULTS, f, indent=2)
    print(f"Detailed results written to docs/api_test_report_{BASE.replace('://','_').replace('/','_')}.json")


if __name__ == "__main__":
    main()
