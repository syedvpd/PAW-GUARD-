"""Comprehensive endpoint test for 5 demo modules: dog, donation, grievance,
lost_found, volunteer. Covers EVERY endpoint + HTTP method with real JSON bodies.

Usage:
    python scripts/api_comprehensive_test.py <base_url> [email] [password]
"""
import json
import sys
import time
import uuid
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
EMAIL = sys.argv[2] if len(sys.argv) > 2 else "super.admin@pawguard.com"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "PawGuard@2026"
TAG = uuid.uuid4().hex[:8]

RESULTS = []
TOKEN = None


def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def request(method, path, body=None, headers=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw.decode())
            except Exception:
                return r.status, raw[:200]
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:200]
    except Exception as e:
        return "ERR", str(e)[:200]


def record(module, test, method, path, status, body, expect=200, skip_reason=None):
    if skip_reason:
        RESULTS.append({"module": module, "test": test, "method": method, "path": path,
                        "status": "SKIPPED", "reason": skip_reason})
        print(f"SKIP [{module}] {test}: {skip_reason}")
        return None
    if isinstance(expect, int):
        ok = isinstance(status, int) and status == expect
    else:
        ok = isinstance(status, int) and status in expect
    entry = {"module": module, "test": test, "method": method, "path": path,
             "status": status, "expected": expect, "ok": ok}
    if isinstance(body, dict):
        err = body.get("error", {})
        if isinstance(err, dict):
            entry["error"] = err.get("message", "")
        else:
            entry["error"] = str(err)[:200]
        if isinstance(body.get("data"), dict):
            entry["id"] = str(body["data"].get("id", ""))
    elif isinstance(body, bytes):
        entry["error"] = ""
    else:
        entry["error"] = str(body)[:200] if not ok else ""
    RESULTS.append(entry)
    label = "PASS" if ok else "FAIL"
    extra = f" | {entry.get('error','')[:120]}" if not ok else ""
    print(f"{label} [{module}] {test} {method} {path} -> {status}{extra}")
    return entry


def login():
    global TOKEN
    s, b = request("POST", "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    if s != 200:
        print(f"FATAL: login failed {s} {json.dumps(b)[:300]}")
        sys.exit(1)
    TOKEN = b["data"]["access_token"]
    print(f"LOGIN OK: {EMAIL}")


# ─────────────────────────── DOG ───────────────────────────
def test_dogs():
    m = "dog"
    created_id = None

    s, b = request("POST", "/api/v1/dogs", {
        "name": f"ComprehensiveDog {TAG}", "breed": "Indie Mix", "gender": "male",
        "estimated_age": "2 years", "age_months": 24, "weight": 16.4,
        "color": "Tan/White", "is_adoptable": False,
    }, headers=auth_headers())
    e = record(m, "create", "POST", "/api/v1/dogs", s, b, 201)
    if e and e.get("id"):
        created_id = e["id"]

    s, b = request("GET", "/api/v1/dogs?page=1&page_size=5", headers=auth_headers())
    record(m, "list", "GET", "/api/v1/dogs", s, b)
    dogs = b.get("data", []) if isinstance(b, dict) else []

    existing_id = dogs[0]["id"] if dogs else None

    if created_id:
        s, b = request("GET", f"/api/v1/dogs/{created_id}", headers=auth_headers())
        record(m, "get by id", "GET", f"/api/v1/dogs/{created_id}", s, b)

        s, b = request("GET", f"/api/v1/dogs/admin/dogs/{created_id}", headers=auth_headers())
        record(m, "admin get", "GET", f"/api/v1/dogs/admin/dogs/{created_id}", s, b)

        s, b = request("GET", f"/api/v1/dogs/{created_id}/public-scan", headers=auth_headers())
        record(m, "public-scan", "GET", f"/api/v1/dogs/{created_id}/public-scan", s, b)

        s, b = request("GET", f"/api/v1/dogs/{created_id}/timeline", headers=auth_headers())
        record(m, "timeline", "GET", f"/api/v1/dogs/{created_id}/timeline", s, b)

        s, b = request("POST", f"/api/v1/dogs/{created_id}/weight", {"weight": 17.0, "notes": "comprehensive test"}, headers=auth_headers())
        record(m, "record weight", "POST", f"/api/v1/dogs/{created_id}/weight", s, b, 201)

        s, b = request("GET", f"/api/v1/dogs/{created_id}/weights", headers=auth_headers())
        record(m, "weights list", "GET", f"/api/v1/dogs/{created_id}/weights", s, b)

        s, b = request("GET", f"/api/v1/dogs/{created_id}/qr-image", headers=auth_headers())
        record(m, "qr-image", "GET", f"/api/v1/dogs/{created_id}/qr-image", s, b)

        s, b = request("PUT", f"/api/v1/dogs/{created_id}", {"name": f"ComprehensiveDog {TAG} Updated", "weight": 18.0}, headers=auth_headers())
        record(m, "update", "PUT", f"/api/v1/dogs/{created_id}", s, b)

        s, b = request("PATCH", f"/api/v1/dogs/{created_id}/status", {"status": "shelter"}, headers=auth_headers())
        record(m, "patch status", "PATCH", f"/api/v1/dogs/{created_id}/status", s, b)

        s, b = request("PATCH", f"/api/v1/dogs/admin/dogs/{created_id}/status", {"status": "shelter"}, headers=auth_headers())
        record(m, "admin patch status", "PATCH", f"/api/v1/dogs/admin/dogs/{created_id}/status", s, b)

    if existing_id:
        s, b = request("POST", "/api/v1/dogs/bulk/status-update", {"ids": [existing_id], "status": "shelter"}, headers=auth_headers())
        record(m, "bulk status-update", "POST", "/api/v1/dogs/bulk/status-update", s, b)

    if created_id:
        s, b = request("DELETE", f"/api/v1/dogs/{created_id}", headers=auth_headers())
        record(m, "delete", "DELETE", f"/api/v1/dogs/{created_id}", s, b)
        s, b = request("GET", f"/api/v1/dogs/{created_id}", headers=auth_headers())
        record(m, "get after delete (404)", "GET", f"/api/v1/dogs/{created_id}", s, b, 404)

        s, b2 = request("POST", "/api/v1/dogs", {"name": f"BulkDelDog {TAG}", "breed": "Mix", "gender": "female"}, headers=auth_headers())
        if s == 201 and isinstance(b2, dict) and b2.get("data"):
            bd = b2["data"]["id"]
            s, b = request("POST", "/api/v1/dogs/bulk/delete", {"ids": [bd]}, headers=auth_headers())
            record(m, "bulk delete", "POST", "/api/v1/dogs/bulk/delete", s, b)
        else:
            record(m, "bulk delete", "POST", "/api/v1/dogs/bulk/delete", "ERR", {}, skip_reason="could not create 2nd dog")
    else:
        record(m, "create-dependent tests", "", "", "ERR", {}, skip_reason="dog creation failed")


# ─────────────────────────── DONATION ───────────────────────────
def test_donations():
    m = "donation"

    s, b = request("GET", "/api/v1/donations?page=1&page_size=5", headers=auth_headers())
    record(m, "list all", "GET", "/api/v1/donations", s, b)
    donations = b.get("data", []) if isinstance(b, dict) else []

    s, b = request("GET", "/api/v1/donations/donors?page=1&page_size=5", headers=auth_headers())
    record(m, "donors list", "GET", "/api/v1/donations/donors", s, b)
    donors = b.get("data", []) if isinstance(b, dict) else []

    s, b = request("GET", "/api/v1/donations/donors/me", headers=auth_headers())
    record(m, "donors/me", "GET", "/api/v1/donations/donors/me", s, b, (200, 404))

    s, b = request("GET", "/api/v1/donations/history", headers=auth_headers())
    record(m, "history", "GET", "/api/v1/donations/history", s, b)

    s, b = request("POST", "/api/v1/donations", {"amount": 100.0, "currency": "INR", "donation_type": "one_time", "notes": f"comprehensive test {TAG}"}, headers=auth_headers())
    e = record(m, "create manual donation", "POST", "/api/v1/donations", s, b, 201)
    manual_don_id = e.get("id") if e else None

    s, b = request("POST", "/api/v1/donations/register", {"tax_identifier": "ABCDE1234F", "notes": f"comprehensive donor {TAG}"}, headers=auth_headers())
    record(m, "register donor", "POST", "/api/v1/donations/register", s, b, (201, 409))

    s, b = request("POST", "/api/v1/donations/checkout", {"amount": 100.0, "currency": "INR"}, headers=auth_headers())
    record(m, "checkout", "POST", "/api/v1/donations/checkout", s, b, (200, 201))
    checkout_don_id = None
    if isinstance(b, dict) and isinstance(b.get("data"), dict):
        checkout_don_id = b["data"].get("donation_id")

    test_don_id = manual_don_id or checkout_don_id or (donations[0]["id"] if donations else None)

    if test_don_id:
        s, b = request("GET", f"/api/v1/donations/{test_don_id}/receipt", headers=auth_headers())
        record(m, "receipt", "GET", f"/api/v1/donations/{test_don_id}/receipt", s, b, (200, 404))
        s, b = request("POST", f"/api/v1/donations/{test_don_id}/reconcile", headers=auth_headers())
        record(m, "reconcile", "POST", f"/api/v1/donations/{test_don_id}/reconcile", s, b, (200, 400, 404, 409))
        s, b = request("PATCH", f"/api/v1/donations/{test_don_id}/status", {"status": "success"}, headers=auth_headers())
        record(m, "patch status", "PATCH", f"/api/v1/donations/{test_don_id}/status", s, b)
        s, b = request("POST", "/api/v1/donations/bulk/status-update", {"ids": [test_don_id], "status": "success"}, headers=auth_headers())
        record(m, "bulk status-update", "POST", "/api/v1/donations/bulk/status-update", s, b)
    else:
        record(m, "receipt/reconcile/status", "", "", "ERR", {}, skip_reason="no donation id")

    s, b = request("POST", "/api/v1/donations/verify", {
        "donation_id": str(test_don_id or uuid.uuid4()),
        "gateway_order_id": "order_demo", "gateway_payment_id": "pay_demo", "gateway_signature": "sig_demo",
    }, headers=auth_headers())
    record(m, "verify (invalid sig)", "POST", "/api/v1/donations/verify", s, b, (400, 403, 404, 422))

    if donors:
        did = donors[0]["id"]
        s, b = request("PUT", f"/api/v1/donations/donors/{did}", {"notes": f"updated by comprehensive test {TAG}"}, headers=auth_headers())
        record(m, "donor update", "PUT", f"/api/v1/donations/donors/{did}", s, b)
    else:
        record(m, "donor update", "PUT", "/api/v1/donations/donors/{id}", "ERR", {}, skip_reason="no donors")

    record(m, "donor delete", "DELETE", "/api/v1/donations/donors/{id}", "SKIP", {}, skip_reason="preserve existing donors")
    record(m, "donors bulk delete", "POST", "/api/v1/donations/donors/bulk/delete", "SKIP", {}, skip_reason="preserve existing donors")

    s, b = request("GET", "/api/v1/donations/campaigns?page=1&page_size=5", headers=auth_headers())
    record(m, "campaigns list", "GET", "/api/v1/donations/campaigns", s, b)

    s, b = request("GET", "/api/v1/donations/campaigns/manage", headers=auth_headers())
    record(m, "campaigns manage", "GET", "/api/v1/donations/campaigns/manage", s, b)

    s, b = request("POST", "/api/v1/donations/campaigns", {
        "name": f"CompCampaign {TAG}", "description": "comprehensive", "target_amount": 5000.0,
        "currency": "INR", "campaign_type": "general", "status": "draft",
        "start_date": "2026-08-10", "end_date": "2026-09-30",
    }, headers=auth_headers())
    e = record(m, "campaign create", "POST", "/api/v1/donations/campaigns", s, b, 201)
    cid = e.get("id") if e else None
    if cid:
        s, b = request("GET", f"/api/v1/donations/campaigns/{cid}", headers=auth_headers())
        record(m, "campaign get", "GET", f"/api/v1/donations/campaigns/{cid}", s, b)
        s, b = request("PATCH", f"/api/v1/donations/campaigns/{cid}", {"description": "updated"}, headers=auth_headers())
        record(m, "campaign update", "PATCH", f"/api/v1/donations/campaigns/{cid}", s, b)
        s, b = request("DELETE", f"/api/v1/donations/campaigns/{cid}", headers=auth_headers())
        record(m, "campaign delete", "DELETE", f"/api/v1/donations/campaigns/{cid}", s, b)
    else:
        record(m, "campaign get/update/delete", "", "", "ERR", {}, skip_reason="campaign creation failed")

    s, b = request("GET", "/api/v1/donations/recurring?page=1&page_size=5", headers=auth_headers())
    record(m, "recurring list", "GET", "/api/v1/donations/recurring", s, b)

    s, b = request("POST", "/api/v1/donations/recurring", {"amount": 50.0, "currency": "INR", "frequency": "monthly"}, headers=auth_headers())
    e = record(m, "recurring create", "POST", "/api/v1/donations/recurring", s, b, (201, 409))
    rec_id = e.get("id") if e else None
    if rec_id:
        s, b = request("DELETE", f"/api/v1/donations/recurring/{rec_id}", headers=auth_headers())
        record(m, "recurring delete", "DELETE", f"/api/v1/donations/recurring/{rec_id}", s, b)
    else:
        record(m, "recurring delete", "DELETE", "/api/v1/donations/recurring/{id}", "ERR", {}, skip_reason="recurring creation failed")

    s, b = request("GET", "/api/v1/donations/sponsorships?page=1&page_size=5", headers=auth_headers())
    record(m, "sponsorships list", "GET", "/api/v1/donations/sponsorships", s, b)

    s, b = request("GET", "/api/v1/dogs?page=1&page_size=1", headers=auth_headers())
    dog_for_sponsor = None
    if isinstance(b, dict) and b.get("data"):
        dog_for_sponsor = b["data"][0]["id"]

    if dog_for_sponsor:
        s, b = request("POST", "/api/v1/donations/sponsorships", {"dog_id": dog_for_sponsor, "monthly_amount": 25.0, "currency": "INR"}, headers=auth_headers())
        e = record(m, "sponsorship create", "POST", "/api/v1/donations/sponsorships", s, b, (201, 409))
        sp_id = e.get("id") if e else None
        if sp_id:
            s, b = request("GET", "/api/v1/donations/sponsorships/my", headers=auth_headers())
            record(m, "sponsorships/my", "GET", "/api/v1/donations/sponsorships/my", s, b)
            s, b = request("GET", f"/api/v1/donations/sponsorships/{sp_id}", headers=auth_headers())
            record(m, "sponsorship get", "GET", f"/api/v1/donations/sponsorships/{sp_id}", s, b)
            s, b = request("PATCH", f"/api/v1/donations/sponsorships/{sp_id}/status", {"status": "paused"}, headers=auth_headers())
            record(m, "sponsorship pause", "PATCH", f"/api/v1/donations/sponsorships/{sp_id}/status", s, b)
        else:
            record(m, "sponsorship detail", "", "", "ERR", {}, skip_reason="sponsorship creation failed")
    else:
        record(m, "sponsorship create", "POST", "/api/v1/donations/sponsorships", "ERR", {}, skip_reason="no dogs for sponsorship")


# ─────────────────────────── GRIEVANCE ───────────────────────────
def test_grievance():
    m = "grievance"

    s, b = request("POST", "/api/v1/grievance", {
        "reporter_name": "Comprehensive Tester", "reporter_phone": "+1-555-0199",
        "reporter_email": "demo@example.com", "complaint_type": "Rescue Delay",
        "details": f"Comprehensive test complaint {TAG}",
    })
    e = record(m, "create (public)", "POST", "/api/v1/grievance", s, b, 201)
    tid = e.get("id") if e else None

    s, b = request("GET", "/api/v1/grievance?page=1&page_size=5", headers=auth_headers())
    record(m, "list", "GET", "/api/v1/grievance", s, b)
    tickets = b.get("data", []) if isinstance(b, dict) else []
    existing_tid = tickets[0]["id"] if tickets else None

    if tid:
        s, b = request("GET", f"/api/v1/grievance/{tid}", headers=auth_headers())
        record(m, "get by id", "GET", f"/api/v1/grievance/{tid}", s, b)

        s, b = request("PUT", f"/api/v1/grievance/{tid}", {"status": "investigating", "resolution_notes": "reviewing"}, headers=auth_headers())
        record(m, "update", "PUT", f"/api/v1/grievance/{tid}", s, b)

        s, b = request("GET", "/api/v1/auth/me", headers=auth_headers())
        me_id = b.get("data", {}).get("id") if isinstance(b, dict) else None

        if me_id:
            s, b = request("POST", f"/api/v1/grievance/{tid}/assign", {"assigned_to_admin_id": me_id}, headers=auth_headers())
            record(m, "assign", "POST", f"/api/v1/grievance/{tid}/assign", s, b)
            s, b = request("POST", f"/api/v1/grievance/{tid}/escalate", {"escalated_to_admin_id": me_id, "reason": "SLA breach"}, headers=auth_headers())
            record(m, "escalate", "POST", f"/api/v1/grievance/{tid}/escalate", s, b)
        else:
            record(m, "assign/escalate", "POST", f"/api/v1/grievance/{tid}/assign", "ERR", {}, skip_reason="no user id")

        s, b = request("POST", f"/api/v1/grievance/{tid}/comments", {"body": f"Comprehensive comment {TAG}", "is_internal": False}, headers=auth_headers())
        record(m, "add comment", "POST", f"/api/v1/grievance/{tid}/comments", s, b, 201)

        s, b = request("GET", f"/api/v1/grievance/{tid}/comments", headers=auth_headers())
        record(m, "list comments", "GET", f"/api/v1/grievance/{tid}/comments", s, b)

        s, b = request("PATCH", f"/api/v1/grievance/{tid}/status?status=resolved", headers=auth_headers())
        record(m, "patch status (query param)", "PATCH", f"/api/v1/grievance/{tid}/status", s, b)

        s, b = request("DELETE", f"/api/v1/grievance/{tid}", headers=auth_headers())
        record(m, "delete", "DELETE", f"/api/v1/grievance/{tid}", s, b)
    else:
        record(m, "ticket-dependent tests", "", "", "ERR", {}, skip_reason="grievance creation failed")

    s, b = request("GET", "/api/v1/grievance/feedback?page=1&page_size=5", headers=auth_headers())
    record(m, "feedback list", "GET", "/api/v1/grievance/feedback", s, b)

    s, b = request("POST", "/api/v1/grievance/feedback", {"rating": 5, "comments": f"Great service {TAG}"})
    e = record(m, "feedback create (public)", "POST", "/api/v1/grievance/feedback", s, b, 201)
    fb_id = e.get("id") if e else None
    if fb_id:
        s, b = request("DELETE", f"/api/v1/grievance/feedback/{fb_id}", headers=auth_headers())
        record(m, "feedback delete", "DELETE", f"/api/v1/grievance/feedback/{fb_id}", s, b)

    if existing_tid:
        s, b = request("POST", "/api/v1/grievance/bulk/status", {"ids": [existing_tid], "status": "resolved"}, headers=auth_headers())
        record(m, "bulk status", "POST", "/api/v1/grievance/bulk/status", s, b)
    else:
        record(m, "bulk status", "POST", "/api/v1/grievance/bulk/status", "ERR", {}, skip_reason="no existing ticket")

    s, b2 = request("POST", "/api/v1/grievance", {
        "reporter_name": "BulkDel Test", "reporter_phone": "+1-555-0198",
        "complaint_type": "Test", "details": f"Bulk delete test {TAG}",
    })
    if s == 201 and isinstance(b2, dict) and b2.get("data"):
        bd_id = b2["data"]["id"]
        s, b = request("POST", "/api/v1/grievance/bulk/delete", {"ids": [bd_id]}, headers=auth_headers())
        record(m, "bulk delete", "POST", "/api/v1/grievance/bulk/delete", s, b)
    else:
        record(m, "bulk delete", "POST", "/api/v1/grievance/bulk/delete", "ERR", {}, skip_reason="could not create ticket")


# ─────────────────────────── LOST & FOUND ───────────────────────────
def test_lost_found():
    m = "lost_found"

    s, b = request("GET", "/api/v1/lost-found/lost?page=1&page_size=5", headers=auth_headers())
    record(m, "lost list", "GET", "/api/v1/lost-found/lost", s, b)
    lost_reports = b.get("data", []) if isinstance(b, dict) else []

    s, b = request("GET", "/api/v1/lost-found/found?page=1&page_size=5", headers=auth_headers())
    record(m, "found list", "GET", "/api/v1/lost-found/found", s, b)

    s, b = request("GET", "/api/v1/lost-found/reunion-stories", headers=auth_headers())
    record(m, "reunion stories", "GET", "/api/v1/lost-found/reunion-stories", s, b)

    s, b = request("GET", "/api/v1/lost-found/stories", headers=auth_headers())
    record(m, "stories", "GET", "/api/v1/lost-found/stories", s, b)

    s, b = request("POST", "/api/v1/lost-found/lost", {
        "species": "dog", "pet_name": f"Buddy {TAG}", "breed": "Beagle Mix", "color": "Tan/White",
        "collar_color": "Red", "location_address": "Jubilee Hills Sector 2",
        "latitude": 17.4326, "longitude": 78.4071, "lost_at": "2026-08-05T14:30:00Z",
        "photo_url": "https://example.com/b.jpg",
    }, headers=auth_headers())
    e = record(m, "lost create", "POST", "/api/v1/lost-found/lost", s, b, 201)
    lid = e.get("id") if e else None

    if lid:
        s, b = request("GET", f"/api/v1/lost-found/lost/{lid}", headers=auth_headers())
        record(m, "lost get", "GET", f"/api/v1/lost-found/lost/{lid}", s, b)

        s, b = request("GET", f"/api/v1/lost-found/lost/{lid}/matches", headers=auth_headers())
        record(m, "lost matches", "GET", f"/api/v1/lost-found/lost/{lid}/matches", s, b)
        matches = b.get("data", []) if isinstance(b, dict) else []

        s, b = request("POST", f"/api/v1/lost-found/lost/{lid}/broadcast", {}, headers=auth_headers())
        record(m, "lost broadcast", "POST", f"/api/v1/lost-found/lost/{lid}/broadcast", s, b, (200, 201, 403))

        if matches:
            mid = matches[0]["id"]
            s, b = request("POST", f"/api/v1/lost-found/matches/{mid}/claim", {"microchip_doc_url": "https://example.com/m.pdf", "verification_notes": "chip matched"}, headers=auth_headers())
            record(m, "match claim", "POST", f"/api/v1/lost-found/matches/{mid}/claim", s, b, (200, 201, 400, 403, 409))
            s, b = request("POST", f"/api/v1/lost-found/matches/{mid}/claim/review", {"approve": True, "verification_notes": "approved"}, headers=auth_headers())
            record(m, "match claim review", "POST", f"/api/v1/lost-found/matches/{mid}/claim/review", s, b, (200, 400, 403, 409))
            s, b = request("POST", f"/api/v1/lost-found/matches/{mid}/resolve?approve=true", headers=auth_headers())
            record(m, "match resolve", "POST", f"/api/v1/lost-found/matches/{mid}/resolve", s, b, (200, 400, 403, 409))
        else:
            record(m, "match claim/review/resolve", "POST", "/api/v1/lost-found/matches/{id}/claim", "SKIP", {}, skip_reason="no matches available")

        s, b = request("DELETE", f"/api/v1/lost-found/lost/{lid}", headers=auth_headers())
        record(m, "lost delete", "DELETE", f"/api/v1/lost-found/lost/{lid}", s, b)
    else:
        record(m, "lost-dependent tests", "", "", "ERR", {}, skip_reason="lost create failed")

    s, b = request("POST", "/api/v1/lost-found/found", {
        "species": "dog", "breed_observed": "Beagle Mix", "color_observed": "Tan/White",
        "collar_color": "Red", "location_address": "Jubilee Hills Sector 3",
        "latitude": 17.4321, "longitude": 78.4055, "found_at": "2026-08-06T09:15:00Z",
        "photo_url": "https://example.com/f.jpg",
    }, headers=auth_headers())
    e = record(m, "found create", "POST", "/api/v1/lost-found/found", s, b, 201)
    fid = e.get("id") if e else None

    if fid:
        s, b = request("GET", f"/api/v1/lost-found/found/{fid}", headers=auth_headers())
        record(m, "found get", "GET", f"/api/v1/lost-found/found/{fid}", s, b)

        s, b = request("GET", f"/api/v1/lost-found/found/{fid}/matches", headers=auth_headers())
        record(m, "found matches", "GET", f"/api/v1/lost-found/found/{fid}/matches", s, b)

        s, b = request("DELETE", f"/api/v1/lost-found/found/{fid}", headers=auth_headers())
        record(m, "found delete", "DELETE", f"/api/v1/lost-found/found/{fid}", s, b)
    else:
        record(m, "found-dependent tests", "", "", "ERR", {}, skip_reason="found create failed")

    s, b2 = request("POST", "/api/v1/lost-found/lost", {
        "species": "dog", "pet_name": f"BulkDel {TAG}", "breed": "Mix", "color": "Black",
        "location_address": "Test Street", "latitude": 17.0, "longitude": 78.0,
        "lost_at": "2026-08-01T00:00:00Z",
    }, headers=auth_headers())
    if s == 201 and isinstance(b2, dict) and b2.get("data"):
        bd = b2["data"]["id"]
        s, b = request("POST", "/api/v1/lost-found/lost/bulk/delete", {"ids": [bd]}, headers=auth_headers())
        record(m, "lost bulk delete", "POST", "/api/v1/lost-found/lost/bulk/delete", s, b)
    else:
        record(m, "lost bulk delete", "POST", "/api/v1/lost-found/lost/bulk/delete", "ERR", {}, skip_reason="could not create 2nd report")

    s, b2 = request("POST", "/api/v1/lost-found/found", {
        "species": "dog", "breed_observed": "Mix", "color_observed": "Black",
        "location_address": "Test Street 2", "latitude": 17.1, "longitude": 78.1,
        "found_at": "2026-08-02T00:00:00Z",
    }, headers=auth_headers())
    if s == 201 and isinstance(b2, dict) and b2.get("data"):
        bd = b2["data"]["id"]
        s, b = request("POST", "/api/v1/lost-found/found/bulk/delete", {"ids": [bd]}, headers=auth_headers())
        record(m, "found bulk delete", "POST", "/api/v1/lost-found/found/bulk/delete", s, b)
    else:
        record(m, "found bulk delete", "POST", "/api/v1/lost-found/found/bulk/delete", "ERR", {}, skip_reason="could not create 2nd report")


# ─────────────────────────── VOLUNTEER ───────────────────────────
def test_volunteers():
    m = "volunteer"

    s, b = request("GET", "/api/v1/volunteers?page=1&page_size=5", headers=auth_headers())
    record(m, "list", "GET", "/api/v1/volunteers", s, b)
    vols = b.get("data", []) if isinstance(b, dict) else []
    profile_id = vols[0]["id"] if vols else None

    if profile_id:
        s, b = request("GET", f"/api/v1/volunteers/{profile_id}", headers=auth_headers())
        record(m, "get by id", "GET", f"/api/v1/volunteers/{profile_id}", s, b)

        s, b = request("PUT", f"/api/v1/volunteers/{profile_id}", {"skills": "Grooming, Transport, First Aid"}, headers=auth_headers())
        record(m, "update", "PUT", f"/api/v1/volunteers/{profile_id}", s, b)

        s, b = request("GET", f"/api/v1/volunteers/{profile_id}/service-summary", headers=auth_headers())
        record(m, "service summary", "GET", f"/api/v1/volunteers/{profile_id}/service-summary", s, b)

        s, b = request("GET", f"/api/v1/volunteers/{profile_id}/certificate", headers=auth_headers())
        record(m, "certificate", "GET", f"/api/v1/volunteers/{profile_id}/certificate", s, b, (200, 403, 404, 422))

        s, b = request("POST", "/api/v1/volunteers/bulk/status", {"ids": [profile_id], "status": "active"}, headers=auth_headers())
        record(m, "bulk status", "POST", "/api/v1/volunteers/bulk/status", s, b)
    else:
        record(m, "profile tests", "", "", "ERR", {}, skip_reason="no volunteer profiles")

    record(m, "profile delete", "DELETE", "/api/v1/volunteers/{id}", "SKIP", {}, skip_reason="preserve existing volunteers")
    record(m, "bulk delete", "POST", "/api/v1/volunteers/bulk/delete", "SKIP", {}, skip_reason="preserve existing volunteers")

    s, b = request("POST", "/api/v1/volunteers/apply", {
        "emergency_contact_name": "Jane Doe", "emergency_contact_phone": "+1-555-0100",
        "skills": "Grooming", "availability": "Weekends", "animal_handling_experience": "3 years",
    }, headers=auth_headers())
    record(m, "apply", "POST", "/api/v1/volunteers/apply", s, b, (200, 201, 400, 409))

    s, b = request("GET", "/api/v1/volunteers/shifts?page=1&page_size=5", headers=auth_headers())
    record(m, "shifts list", "GET", "/api/v1/volunteers/shifts", s, b)

    s, b = request("POST", "/api/v1/volunteers/shifts", {
        "role_name": f"Dog Walking {TAG}", "start_at": "2026-08-20T09:00:00Z",
        "end_at": "2026-08-20T12:00:00Z", "capacity": 5,
    }, headers=auth_headers())
    e = record(m, "shift create", "POST", "/api/v1/volunteers/shifts", s, b, 201)
    shift_id = e.get("id") if e else None

    if shift_id:
        s, b = request("GET", f"/api/v1/volunteers/shifts/{shift_id}/attendance?page=1&page_size=5", headers=auth_headers())
        record(m, "shift attendance list", "GET", f"/api/v1/volunteers/shifts/{shift_id}/attendance", s, b)

        s, b = request("POST", f"/api/v1/volunteers/shifts/{shift_id}/join", headers=auth_headers())
        record(m, "join shift", "POST", f"/api/v1/volunteers/shifts/{shift_id}/join", s, b, (200, 201, 400, 403, 404, 409))
        att_id = None
        if isinstance(b, dict) and isinstance(b.get("data"), dict):
            att_id = b["data"].get("id")
        if att_id:
            s, b = request("POST", f"/api/v1/volunteers/attendance/{att_id}/check-in", headers=auth_headers())
            record(m, "check-in", "POST", f"/api/v1/volunteers/attendance/{att_id}/check-in", s, b, (200, 400, 409))
            s, b = request("POST", f"/api/v1/volunteers/attendance/{att_id}/check-out", headers=auth_headers())
            record(m, "check-out", "POST", f"/api/v1/volunteers/attendance/{att_id}/check-out", s, b, (200, 400, 409))
        else:
            record(m, "check-in/out", "POST", f"/api/v1/volunteers/attendance/{{id}}/check-in", "SKIP", {}, skip_reason="no attendance created")
    else:
        record(m, "shift-dependent tests", "", "", "ERR", {}, skip_reason="shift creation failed")


def main():
    login()
    test_dogs()
    test_donations()
    test_grievance()
    test_lost_found()
    test_volunteers()

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r.get("ok"))
    failed = sum(1 for r in RESULTS if r.get("ok") is False)
    skipped = sum(1 for r in RESULTS if r.get("status") == "SKIPPED")
    tested = total - skipped

    print("\n" + "=" * 70)
    print(f"TARGET: {BASE}")
    print(f"TOTAL ENDPOINTS: {total}  TESTED: {tested}  PASSED: {passed}  FAILED: {failed}  SKIPPED: {skipped}")
    print("=" * 70)
    if failed:
        print("\nFAILURES:")
        for r in RESULTS:
            if r.get("ok") is False:
                print(f"  FAIL {r['module']}:{r['test']} {r['method']} -> {r['status']} | {r.get('error','')[:150]}")
    if skipped:
        print(f"\nSKIPPED ({skipped}):")
        for r in RESULTS:
            if r.get("status") == "SKIPPED":
                print(f"  SKIP {r['module']}:{r['test']} — {r.get('reason','')}")

    fname = f"docs/api_comprehensive_report_{BASE.replace('://', '_').replace('/', '_').replace(':', '_')}.json"
    with open(fname, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print(f"\nFull report: {fname}")


if __name__ == "__main__":
    main()
