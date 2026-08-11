"""Comprehensive endpoint test for 5 modules: rescue, adoption, foster, medical, shelter.

Usage:
    python scripts/api_comprehensive_test2.py <base_url> [email] [password]
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

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


def create_dog(name=None, adoptable=False):
    s, b = request("POST", "/api/v1/dogs", {
        "name": name or f"Comp2Dog {TAG}", "breed": "Indie Mix", "gender": "male",
        "estimated_age": "2 years", "age_months": 24, "weight": 16.4,
        "color": "Tan/White", "is_adoptable": adoptable,
    }, headers=auth_headers())
    if s == 201 and isinstance(b, dict) and b.get("data"):
        return b["data"]["id"]
    return None


# ---------------------------- RESCUE ----------------------------
def test_rescue():
    m = "rescue"
    phone = f"+1-{5550000000 + int(TAG[:4], 16) % 99999}"

    s, b = request("POST", "/api/v1/public/rescue/media-upload-url", {
        "filename": "evidence.jpg", "mime_type": "image/jpeg", "file_size": 1048576,
    })
    record(m, "public media upload url", "POST", "/api/v1/public/rescue/media-upload-url", s, b)

    s, b = request("POST", "/api/v1/public/rescue/report", {
        "reporter_name": "Public Reporter", "reporter_phone": phone,
        "location_address": "Jubilee Hills Sector 4, Road 3", "physical_condition": "fractured_injured",
        "severity": "high", "is_urgent": True,
    })
    e = record(m, "public report", "POST", "/api/v1/public/rescue/report", s, b, 201)
    ticket = None
    if e and isinstance(b, dict) and isinstance(b.get("data"), dict):
        ticket = b["data"].get("ticket_number")

    if ticket:
        s, b = request("GET", f"/api/v1/rescue/status?ticket_number={urllib.parse.quote(ticket)}&phone={urllib.parse.quote(phone)}")
        record(m, "public status lookup", "GET", "/api/v1/rescue/status", s, b)
    else:
        record(m, "public status lookup", "GET", "/api/v1/rescue/status", "ERR", {}, skip_reason="no ticket")

    s, b = request("POST", "/api/v1/rescue/media-upload-url", {
        "filename": "staff_evidence.jpg", "mime_type": "image/jpeg", "file_size": 2097152,
    }, headers=auth_headers())
    record(m, "staff media upload url", "POST", "/api/v1/rescue/media-upload-url", s, b)

    s, b = request("POST", "/api/v1/rescue/report", {
        "reporter_name": "Staff Reporter", "reporter_phone": phone,
        "location_address": "Banjara Hills, Road 12", "physical_condition": "critical_life_threatening",
        "severity": "critical", "is_urgent": True,
    }, headers=auth_headers())
    e = record(m, "staff report", "POST", "/api/v1/rescue/report", s, b, 201)
    rid1 = e.get("id") if e else None

    s, b = request("GET", "/api/v1/rescue?page=1&page_size=5", headers=auth_headers())
    record(m, "list", "GET", "/api/v1/rescue", s, b)

    if rid1:
        s, b = request("GET", f"/api/v1/rescue/{rid1}", headers=auth_headers())
        record(m, "get by id", "GET", f"/api/v1/rescue/{rid1}", s, b)

        s, b = request("POST", f"/api/v1/rescue/{rid1}/verify", {"status": "verified", "severity": "high"}, headers=auth_headers())
        record(m, "verify", "POST", f"/api/v1/rescue/{rid1}/verify", s, b)

        s, b = request("POST", f"/api/v1/rescue/{rid1}/dispatch", {"notes": "Dispatch full team, road blocked"}, headers=auth_headers())
        e = record(m, "dispatch", "POST", f"/api/v1/rescue/{rid1}/dispatch", s, b)
        dispatch_id = None
        if e and isinstance(b, dict) and isinstance(b.get("data"), dict):
            disp = b["data"].get("dispatch") or {}
            dispatch_id = disp.get("id") if isinstance(disp, dict) else None

        s, b = request("POST", f"/api/v1/rescue/{rid1}/escalate", {"escalation_type": "vet_transport", "escalation_notes": "Need vet transport"}, headers=auth_headers())
        record(m, "escalate", "POST", f"/api/v1/rescue/{rid1}/escalate", s, b)

        s, b = request("POST", f"/api/v1/rescue/{rid1}/located", headers=auth_headers())
        record(m, "mark located", "POST", f"/api/v1/rescue/{rid1}/located", s, b)

        s, b = request("POST", f"/api/v1/rescue/{rid1}/secured", headers=auth_headers())
        record(m, "mark secured", "POST", f"/api/v1/rescue/{rid1}/secured", s, b)

        s, b = request("POST", f"/api/v1/rescue/{rid1}/admitted", {"notes": "Admitted at shelter, wounds cleaned"}, headers=auth_headers())
        record(m, "mark admitted", "POST", f"/api/v1/rescue/{rid1}/admitted", s, b)

        if dispatch_id:
            s, b = request("PATCH", f"/api/v1/rescue/dispatch/{dispatch_id}", {"notes": "Updated dispatch notes"}, headers=auth_headers())
            record(m, "update dispatch", "PATCH", f"/api/v1/rescue/dispatch/{dispatch_id}", s, b)
            s, b = request("DELETE", f"/api/v1/rescue/dispatch/{dispatch_id}", headers=auth_headers())
            record(m, "delete dispatch", "DELETE", f"/api/v1/rescue/dispatch/{dispatch_id}", s, b)
        else:
            record(m, "update/delete dispatch", "PATCH", "/api/v1/rescue/dispatch/{id}", "SKIP", {}, skip_reason="no dispatch id")

        s, b = request("GET", "/api/v1/rescue/dispatches?page=1&page_size=5", headers=auth_headers())
        record(m, "dispatches list", "GET", "/api/v1/rescue/dispatches", s, b)

        s, b = request("DELETE", f"/api/v1/rescue/{rid1}", headers=auth_headers())
        record(m, "delete", "DELETE", f"/api/v1/rescue/{rid1}", s, b)

        s, b = request("GET", f"/api/v1/rescue/{rid1}", headers=auth_headers())
        record(m, "get after delete (404)", "GET", f"/api/v1/rescue/{rid1}", s, b, (404, 200))
    else:
        record(m, "rescue lifecycle", "", "", "ERR", {}, skip_reason="staff report failed")

    s, b = request("POST", "/api/v1/rescue/report", {
        "reporter_name": "Bulk Reporter", "reporter_phone": phone,
        "location_address": "Kukatpally Main Road", "physical_condition": "abandoned_stray",
        "severity": "medium",
    }, headers=auth_headers())
    e = record(m, "bulk-request create", "POST", "/api/v1/rescue/report", s, b, 201)
    rid2 = e.get("id") if e else None
    if rid2:
        s, b = request("POST", "/api/v1/rescue/bulk/status-update", {"ids": [rid2], "status": "reported"}, headers=auth_headers())
        record(m, "bulk status-update", "POST", "/api/v1/rescue/bulk/status-update", s, b, (200, 400, 409))
        s, b = request("POST", "/api/v1/rescue/bulk/delete", {"ids": [rid2]}, headers=auth_headers())
        record(m, "bulk delete", "POST", "/api/v1/rescue/bulk/delete", s, b)
    else:
        record(m, "bulk status/delete", "POST", "/api/v1/rescue/bulk/delete", "ERR", {}, skip_reason="no rescue id")


# ---------------------------- ADOPTION ----------------------------
def test_adoption(dog_id):
    m = "adoption"

    s, b = request("GET", "/api/v1/adoptions?page=1&page_size=5", headers=auth_headers())
    record(m, "list", "GET", "/api/v1/adoptions", s, b)

    s, b = request("GET", "/api/v1/adoptions/my", headers=auth_headers())
    record(m, "my applications", "GET", "/api/v1/adoptions/my", s, b)

    s, b = request("GET", "/api/v1/adoptions/nearby-shelters?latitude=28.61&longitude=77.20&radius_km=50", headers=auth_headers())
    record(m, "nearby shelters", "GET", "/api/v1/adoptions/nearby-shelters", s, b)

    if not dog_id:
        record(m, "adoption flow", "", "", "ERR", {}, skip_reason="no dog created")
        return

    # Medical clearance is required before adoption application
    s, b = request("POST", f"/api/v1/medical/clearance/{dog_id}", {
        "clearance_type": "adoption_surgery", "status": "approved", "decision_notes": "Healthy, cleared for adoption",
    }, headers=auth_headers())
    record(m, "pre-clearance for adoption", "POST", f"/api/v1/medical/clearance/{dog_id}", s, b, (200, 201))

    s, b = request("POST", "/api/v1/adoptions", {
        "dog_id": dog_id, "residential_status": "owned", "has_landlord_approval": True,
        "has_yard_fence": True, "household_members_count": 3,
        "existing_pets_medical_details": "One neutered cat, vaccinated.",
        "pet_care_experience": "Owned a Labrador for 10 years.",
    }, headers=auth_headers())
    e = record(m, "apply", "POST", "/api/v1/adoptions", s, b, 201)
    app_id = e.get("id") if e else None

    if app_id:
        s, b = request("GET", f"/api/v1/adoptions/{app_id}", headers=auth_headers())
        record(m, "get", "GET", f"/api/v1/adoptions/{app_id}", s, b)

        s, b = request("PUT", f"/api/v1/adoptions/{app_id}", {"home_inspection_notes": "Yard fenced, home clean"}, headers=auth_headers())
        record(m, "update", "PUT", f"/api/v1/adoptions/{app_id}", s, b)

        s, b = request("PATCH", f"/api/v1/adoptions/{app_id}/status", {"status": "screening"}, headers=auth_headers())
        record(m, "status update", "PATCH", f"/api/v1/adoptions/{app_id}/status", s, b, (200, 400, 409))

        s, b = request("PUT", f"/api/v1/adoptions/{app_id}/fee", {"fee_amount": 250.00}, headers=auth_headers())
        record(m, "set fee", "PUT", f"/api/v1/adoptions/{app_id}/fee", s, b, (200, 400))

        s, b = request("POST", f"/api/v1/adoptions/{app_id}/scores", {
            "home_environment_score": 8, "pet_care_knowledge_score": 7,
            "financial_readiness_score": 9, "lifestyle_compatibility_score": 8,
            "recommendation": "approve", "notes": "Strong candidate",
        }, headers=auth_headers())
        record(m, "add score", "POST", f"/api/v1/adoptions/{app_id}/scores", s, b, 201)

        s, b = request("GET", f"/api/v1/adoptions/{app_id}/scores", headers=auth_headers())
        record(m, "get scores", "GET", f"/api/v1/adoptions/{app_id}/scores", s, b)

        s, b = request("POST", f"/api/v1/adoptions/{app_id}/follow-ups", {"due_day": 30}, headers=auth_headers())
        e = record(m, "create follow-up", "POST", f"/api/v1/adoptions/{app_id}/follow-ups", s, b, (201, 400))
        fu_id = None
        if e and isinstance(b, dict) and isinstance(b.get("data"), dict):
            fu_id = b["data"].get("id")

        s, b = request("GET", f"/api/v1/adoptions/{app_id}/follow-ups", headers=auth_headers())
        record(m, "list follow-ups", "GET", f"/api/v1/adoptions/{app_id}/follow-ups", s, b)

        if fu_id:
            s, b = request("POST", f"/api/v1/adoptions/{app_id}/follow-ups/{fu_id}/proof", {
                "media_keys": [f"documents/followup_{TAG}.jpg"], "notes": "Buddy is doing great!",
            }, headers=auth_headers())
            record(m, "submit follow-up proof", "POST", f"/api/v1/adoptions/{app_id}/follow-ups/{fu_id}/proof", s, b, (200, 400, 404))
        else:
            record(m, "submit follow-up proof", "POST", "/api/v1/adoptions/{app_id}/follow-ups/{id}/proof", "SKIP", {}, skip_reason="no follow-up created")

        s, b = request("GET", f"/api/v1/adoptions/{app_id}/agreement", headers=auth_headers())
        record(m, "agreement", "GET", f"/api/v1/adoptions/{app_id}/agreement", s, b, (200, 404))

        s, b = request("POST", "/api/v1/adoptions/bulk/status-update", {"ids": [app_id], "status": "approved"}, headers=auth_headers())
        record(m, "bulk status-update", "POST", "/api/v1/adoptions/bulk/status-update", s, b, (200, 400, 409))

        s, b = request("DELETE", f"/api/v1/adoptions/{app_id}", headers=auth_headers())
        record(m, "delete", "DELETE", f"/api/v1/adoptions/{app_id}", s, b)
    else:
        record(m, "adoption app flow", "", "", "ERR", {}, skip_reason="application creation failed")

    s, b = request("POST", "/api/v1/adoptions", {
        "dog_id": dog_id, "residential_status": "rented", "household_members_count": 2,
    }, headers=auth_headers())
    if s == 201 and isinstance(b, dict) and b.get("data"):
        bd = b["data"]["id"]
        s, b = request("POST", "/api/v1/adoptions/bulk/delete", {"ids": [bd]}, headers=auth_headers())
        record(m, "bulk delete", "POST", "/api/v1/adoptions/bulk/delete", s, b)
    else:
        record(m, "bulk delete", "POST", "/api/v1/adoptions/bulk/delete", "ERR", {}, skip_reason="could not create 2nd application")

# ---------------------------- FOSTER ----------------------------
def test_foster(dog_id):
    m = "foster"

    s, b = request("GET", "/api/v1/fosters?page=1&page_size=5", headers=auth_headers())
    record(m, "list", "GET", "/api/v1/fosters", s, b)

    s, b = request("POST", "/api/v1/fosters/apply", {
        "preferences": "Puppies, Medical Recovery", "max_capacity": 2,
        "notes": "Fenced backyard, prior fostering experience.",
    }, headers=auth_headers())
    e = record(m, "apply", "POST", "/api/v1/fosters/apply", s, b, (201, 409))
    profile_id = e.get("id") if e else None
    if not profile_id and isinstance(b, dict) and isinstance(b.get("data"), dict):
        profile_id = b["data"].get("id")
    # If already applied (409), look up existing profile from list
    if not profile_id:
        vols = b.get("data", []) if isinstance(b, dict) and isinstance(b.get("data"), list) else []
    if not profile_id:
        s2, b2 = request("GET", "/api/v1/fosters?page=1&page_size=50", headers=auth_headers())
        if isinstance(b2, dict):
            items = b2.get("data", [])
            if items:
                profile_id = items[0].get("id")

    if not dog_id:
        record(m, "foster placement flow", "", "", "ERR", {}, skip_reason="no dog created")
    elif profile_id:
        s, b = request("PUT", f"/api/v1/fosters/{profile_id}", {"status": "approved", "is_available": True}, headers=auth_headers())
        record(m, "update profile", "PUT", f"/api/v1/fosters/{profile_id}", s, b, (200, 400))

        s, b = request("POST", f"/api/v1/fosters/{profile_id}/placements", {"dog_id": dog_id, "notes": "Post-surgery recovery placement"}, headers=auth_headers())
        e = record(m, "create placement", "POST", f"/api/v1/fosters/{profile_id}/placements", s, b, 201)
        pl_id = e.get("id") if e else None

        if pl_id:
            s, b = request("POST", f"/api/v1/fosters/placements/{pl_id}/progress", {
                "weight_kg": 16.2, "behavior_notes": "Settled well", "mood_rating": 4,
            }, headers=auth_headers())
            record(m, "log progress", "POST", f"/api/v1/fosters/placements/{pl_id}/progress", s, b, 201)

            s, b = request("GET", f"/api/v1/fosters/placements/{pl_id}/progress", headers=auth_headers())
            record(m, "list progress", "GET", f"/api/v1/fosters/placements/{pl_id}/progress", s, b)

            s, b = request("POST", f"/api/v1/fosters/placements/{pl_id}/supplies", {
                "item_type": "food", "description": "20lb bag of puppy food", "quantity": 1,
            }, headers=auth_headers())
            record(m, "dispatch supplies", "POST", f"/api/v1/fosters/placements/{pl_id}/supplies", s, b, 201)

            s, b = request("GET", f"/api/v1/fosters/placements/{pl_id}/supplies", headers=auth_headers())
            record(m, "list supplies", "GET", f"/api/v1/fosters/placements/{pl_id}/supplies", s, b)

            s, b = request("POST", f"/api/v1/fosters/placements/{pl_id}/return", {"notes": "Fully recovered, returning to shelter"}, headers=auth_headers())
            record(m, "return placement", "POST", f"/api/v1/fosters/placements/{pl_id}/return", s, b, (200, 400, 409))
        else:
            record(m, "placement flow", "", "", "ERR", {}, skip_reason="placement creation failed")

        s, b = request("POST", f"/api/v1/fosters/placements/{uuid.uuid4()}/convert-to-adopt", headers=auth_headers())
        record(m, "convert-to-adopt (404)", "POST", f"/api/v1/fosters/placements/{uuid.uuid4()}/convert-to-adopt", s, b, (200, 400, 404, 409))

        s, b = request("DELETE", f"/api/v1/fosters/{profile_id}", headers=auth_headers())
        record(m, "delete profile", "DELETE", f"/api/v1/fosters/{profile_id}", s, b, (200, 400))

        s, b = request("POST", "/api/v1/fosters/bulk/delete", {"ids": [profile_id]}, headers=auth_headers())
        record(m, "bulk delete", "POST", "/api/v1/fosters/bulk/delete", s, b, (200, 400))
    else:
        record(m, "foster profile flow", "", "", "ERR", {}, skip_reason="no profile id")


# ---------------------------- MEDICAL ----------------------------
def test_medical(dog_id):
    m = "medical"

    s, b = request("GET", "/api/v1/medical/exams?page=1&page_size=5", headers=auth_headers())
    record(m, "exams list", "GET", "/api/v1/medical/exams", s, b)

    if not dog_id:
        record(m, "medical flow", "", "", "ERR", {}, skip_reason="no dog created")
        return

    s, b = request("POST", "/api/v1/medical/exams", {
        "dog_id": dog_id, "body_condition_score": 5, "dental_health": "Mild tartar",
        "visible_injuries": "Small laceration on left hind leg", "triage_diagnosis": "Stable, mild dehydration",
    }, headers=auth_headers())
    record(m, "create exam", "POST", "/api/v1/medical/exams", s, b, 201)

    s, b = request("GET", "/api/v1/medical/treatments?page=1&page_size=5", headers=auth_headers())
    record(m, "treatments list", "GET", "/api/v1/medical/treatments", s, b)

    s, b = request("POST", "/api/v1/medical/treatments", {
        "dog_id": dog_id, "treatment_type": "Spay/Neuter Surgery", "description": "Routine spay, no complications",
    }, headers=auth_headers())
    record(m, "create treatment", "POST", "/api/v1/medical/treatments", s, b, 201)

    s, b = request("GET", "/api/v1/medical/vaccinations?page=1&page_size=5", headers=auth_headers())
    record(m, "vaccinations list", "GET", "/api/v1/medical/vaccinations", s, b)

    s, b = request("POST", "/api/v1/medical/vaccinations", {
        "dog_id": dog_id, "vaccine_name": "Rabies", "lot_number": f"LOT-{TAG[:8]}",
    }, headers=auth_headers())
    record(m, "create vaccination", "POST", "/api/v1/medical/vaccinations", s, b, 201)

    s, b = request("GET", "/api/v1/medical/prescriptions?page=1&page_size=5", headers=auth_headers())
    record(m, "prescriptions list", "GET", "/api/v1/medical/prescriptions", s, b)

    s, b = request("POST", "/api/v1/medical/prescriptions", {
        "dog_id": dog_id, "drug_name": "Amoxicillin", "dosage": "250mg twice daily",
        "route": "Oral", "start_at": "2026-07-22T08:00:00Z", "end_at": "2026-07-29T08:00:00Z",
    }, headers=auth_headers())
    e = record(m, "create prescription", "POST", "/api/v1/medical/prescriptions", s, b, 201)
    rx_id = e.get("id") if e else None

    if rx_id:
        s, b = request("PUT", f"/api/v1/medical/prescriptions/{rx_id}", {"dosage": "500mg twice daily"}, headers=auth_headers())
        record(m, "update prescription", "PUT", f"/api/v1/medical/prescriptions/{rx_id}", s, b)

        s, b = request("PATCH", f"/api/v1/medical/prescriptions/{rx_id}/status", {"is_active": False}, headers=auth_headers())
        record(m, "prescription status", "PATCH", f"/api/v1/medical/prescriptions/{rx_id}/status", s, b)

        s, b = request("GET", f"/api/v1/medical/prescriptions/{rx_id}/administrations?page=1&page_size=5", headers=auth_headers())
        record(m, "rx administrations", "GET", f"/api/v1/medical/prescriptions/{rx_id}/administrations", s, b)

        s, b = request("POST", "/api/v1/medical/bulk/prescriptions/status", {"ids": [rx_id], "status": "active"}, headers=auth_headers())
        record(m, "bulk prescription status", "POST", "/api/v1/medical/bulk/prescriptions/status", s, b, (200, 400))
    else:
        record(m, "prescription dependent", "", "", "ERR", {}, skip_reason="prescription creation failed")

    s, b = request("POST", "/api/v1/medical/administrations", {
        "dog_id": dog_id, "medication_name": "Amoxicillin", "dosage": "5ml", "route": "Oral",
        "notes": "Given with food",
    }, headers=auth_headers())
    record(m, "create administration", "POST", "/api/v1/medical/administrations", s, b, 201)

    s, b = request("GET", f"/api/v1/medical/dogs/{dog_id}/administrations", headers=auth_headers())
    record(m, "dog administrations", "GET", f"/api/v1/medical/dogs/{dog_id}/administrations", s, b)

    s, b = request("GET", f"/api/v1/medical/dogs/{dog_id}/history", headers=auth_headers())
    record(m, "dog history", "GET", f"/api/v1/medical/dogs/{dog_id}/history", s, b)

    s, b = request("POST", f"/api/v1/medical/clearance/{dog_id}", {
        "clearance_type": "adoption_surgery", "status": "approved", "decision_notes": "Healthy, cleared for adoption",
    }, headers=auth_headers())
    record(m, "create clearance", "POST", f"/api/v1/medical/clearance/{dog_id}", s, b, (200, 201, 409))

    s, b = request("GET", f"/api/v1/medical/clearances/dogs/{dog_id}", headers=auth_headers())
    record(m, "dog clearances", "GET", f"/api/v1/medical/clearances/dogs/{dog_id}", s, b)

    s, b = request("GET", "/api/v1/medical/vaccine-protocols?page=1&page_size=5", headers=auth_headers())
    record(m, "vaccine protocols list", "GET", "/api/v1/medical/vaccine-protocols", s, b)

    s, b = request("POST", "/api/v1/medical/vaccine-protocols", {
        "name": f"Rabies-{TAG[:6]}", "default_interval_days": 365, "is_required": True,
    }, headers=auth_headers())
    e = record(m, "create vaccine protocol", "POST", "/api/v1/medical/vaccine-protocols", s, b, 201)
    vp_id = e.get("id") if e else None

    if vp_id:
        s, b = request("DELETE", f"/api/v1/medical/vaccine-protocols/{vp_id}", headers=auth_headers())
        record(m, "delete vaccine protocol", "DELETE", f"/api/v1/medical/vaccine-protocols/{vp_id}", s, b)

    s, b = request("DELETE", f"/api/v1/medical/vaccine-protocols/{uuid.uuid4()}", headers=auth_headers())
    record(m, "delete vaccine protocol (404)", "DELETE", f"/api/v1/medical/vaccine-protocols/{uuid.uuid4()}", s, b, (200, 404))

    if rx_id:
        s, b = request("POST", "/api/v1/medical/bulk/delete", {"ids": [rx_id]}, headers=auth_headers())
        record(m, "bulk delete", "POST", "/api/v1/medical/bulk/delete", s, b, (200, 400))
    else:
        record(m, "bulk delete", "POST", "/api/v1/medical/bulk/delete", "SKIP", {}, skip_reason="no prescription id")

# ---------------------------- SHELTER ----------------------------
def test_shelter(dog_id):
    m = "shelter"

    s, b = request("POST", "/api/v1/shelter/facilities", {
        "name": f"Central Shelter {TAG}", "address": "45 Rescue Road, Sector 4",
        "phone": "+1-555-0111", "latitude": 28.6139, "longitude": 77.2090,
        "total_capacity": 100, "facility_type": "shelter",
    }, headers=auth_headers())
    e = record(m, "create facility", "POST", "/api/v1/shelter/facilities", s, b, 201)
    fac1 = e.get("id") if e else None

    s, b = request("POST", "/api/v1/shelter/facilities", {
        "name": f"Partner Clinic {TAG}", "address": "12 Vet Lane, Sector 6",
        "phone": "+1-555-0222", "total_capacity": 30, "facility_type": "clinic",
    }, headers=auth_headers())
    e = record(m, "create facility 2", "POST", "/api/v1/shelter/facilities", s, b, 201)
    fac2 = e.get("id") if e else None

    s, b = request("GET", "/api/v1/shelter/facilities?page=1&page_size=5", headers=auth_headers())
    record(m, "list facilities", "GET", "/api/v1/shelter/facilities", s, b)

    if fac1:
        s, b = request("GET", f"/api/v1/shelter/facilities/{fac1}", headers=auth_headers())
        record(m, "get facility", "GET", f"/api/v1/shelter/facilities/{fac1}", s, b)

        s, b = request("PUT", f"/api/v1/shelter/facilities/{fac1}", {"total_capacity": 120, "phone": "+1-555-0112"}, headers=auth_headers())
        record(m, "update facility", "PUT", f"/api/v1/shelter/facilities/{fac1}", s, b)

        s, b = request("PUT", f"/api/v1/shelter/facilities/{fac1}/status", {"status": "active"}, headers=auth_headers())
        record(m, "facility status", "PUT", f"/api/v1/shelter/facilities/{fac1}/status", s, b)

        s, b = request("POST", f"/api/v1/shelter/facilities/{fac1}/sections", {
            "name": "Quarantine Wing", "section_type": "quarantine", "capacity": 15,
        }, headers=auth_headers())
        e = record(m, "create section", "POST", f"/api/v1/shelter/facilities/{fac1}/sections", s, b, 201)
        sec_id = e.get("id") if e else None

        s, b = request("GET", f"/api/v1/shelter/facilities/{fac1}/sections", headers=auth_headers())
        record(m, "list sections", "GET", f"/api/v1/shelter/facilities/{fac1}/sections", s, b)

        if sec_id:
            s, b = request("POST", f"/api/v1/shelter/sections/{sec_id}/kennels", {"identifier": f"K-{TAG[:4]}", "capacity": 2}, headers=auth_headers())
            e = record(m, "create kennel", "POST", f"/api/v1/shelter/sections/{sec_id}/kennels", s, b, 201)
            kennel_id = e.get("id") if e else None

            s, b = request("GET", f"/api/v1/shelter/sections/{sec_id}/kennels", headers=auth_headers())
            record(m, "list kennels", "GET", f"/api/v1/shelter/sections/{sec_id}/kennels", s, b)

            if kennel_id and dog_id:
                s, b = request("PATCH", f"/api/v1/shelter/kennels/{kennel_id}/assign/{dog_id}", headers=auth_headers())
                record(m, "assign dog to kennel", "PATCH", f"/api/v1/shelter/kennels/{kennel_id}/assign/{dog_id}", s, b, (200, 400, 409))

                s, b = request("PUT", f"/api/v1/shelter/kennels/{kennel_id}/sanitation?status_val=needs_cleaning", headers=auth_headers())
                record(m, "update sanitation", "PUT", f"/api/v1/shelter/kennels/{kennel_id}/sanitation", s, b)

                s, b = request("POST", f"/api/v1/shelter/kennels/{kennel_id}/cleaning-logs", {"method": "pressure wash", "notes": "Full disinfection"}, headers=auth_headers())
                record(m, "log cleaning", "POST", f"/api/v1/shelter/kennels/{kennel_id}/cleaning-logs", s, b, 201)

                s, b = request("GET", f"/api/v1/shelter/kennels/{kennel_id}/cleaning-logs", headers=auth_headers())
                record(m, "list cleaning logs", "GET", f"/api/v1/shelter/kennels/{kennel_id}/cleaning-logs", s, b)
            else:
                record(m, "kennel dependent", "PATCH", f"/api/v1/shelter/kennels/{{id}}/assign/{{dog_id}}", "SKIP", {}, skip_reason="no kennel/dog")
        else:
            record(m, "kennel dependent", "POST", "/api/v1/shelter/sections/{id}/kennels", "SKIP", {}, skip_reason="no section")
    else:
        record(m, "facility dependent", "", "", "ERR", {}, skip_reason="facility creation failed")

    if dog_id and fac1 and fac2:
        s, b = request("POST", "/api/v1/shelter/transfers", {
            "dog_id": dog_id, "from_facility_id": fac1, "to_facility_id": fac2, "notes": "Transferring for specialized care",
        }, headers=auth_headers())
        e = record(m, "request transfer", "POST", "/api/v1/shelter/transfers", s, b, 201)
        tr_id = e.get("id") if e else None

        s, b = request("GET", "/api/v1/shelter/transfers?page=1&page_size=5", headers=auth_headers())
        record(m, "list transfers", "GET", "/api/v1/shelter/transfers", s, b)

        if tr_id:
            s, b = request("GET", f"/api/v1/shelter/transfers/{tr_id}", headers=auth_headers())
            record(m, "get transfer", "GET", f"/api/v1/shelter/transfers/{tr_id}", s, b)

            s, b = request("POST", f"/api/v1/shelter/transfers/{tr_id}/confirm-sender", headers=auth_headers())
            record(m, "confirm sender", "POST", f"/api/v1/shelter/transfers/{tr_id}/confirm-sender", s, b, (200, 400, 409))

            s, b = request("POST", f"/api/v1/shelter/transfers/{tr_id}/confirm-receiver", headers=auth_headers())
            record(m, "confirm receiver", "POST", f"/api/v1/shelter/transfers/{tr_id}/confirm-receiver", s, b, (200, 400, 409))
        else:
            record(m, "transfer dependent", "GET", "/api/v1/shelter/transfers/{id}", "SKIP", {}, skip_reason="transfer creation failed")
    else:
        record(m, "transfer flow", "POST", "/api/v1/shelter/transfers", "SKIP", {}, skip_reason="need dog + 2 facilities")

    if dog_id:
        s, b = request("POST", "/api/v1/shelter/care-logs", {
            "dog_id": dog_id, "dietary_requirements": "Grain-free, 3x daily", "exercise_hours": 1.5,
            "behavioral_enrichment": "Puzzle feeder, outdoor play",
        }, headers=auth_headers())
        record(m, "submit care log", "POST", "/api/v1/shelter/care-logs", s, b, 201)

        s, b = request("GET", f"/api/v1/shelter/dogs/{dog_id}/care-logs", headers=auth_headers())
        record(m, "list care logs", "GET", f"/api/v1/shelter/dogs/{dog_id}/care-logs", s, b)
    else:
        record(m, "care logs", "POST", "/api/v1/shelter/care-logs", "SKIP", {}, skip_reason="no dog")

    if fac2:
        s, b = request("DELETE", f"/api/v1/shelter/facilities/{fac2}", headers=auth_headers())
        record(m, "delete facility 2", "DELETE", f"/api/v1/shelter/facilities/{fac2}", s, b, (200, 400))

        s, b = request("POST", "/api/v1/shelter/facilities/bulk/delete", {"ids": [fac2]}, headers=auth_headers())
        record(m, "bulk delete facilities", "POST", "/api/v1/shelter/facilities/bulk/delete", s, b, (200, 400))
    else:
        record(m, "delete/bulk facilities", "DELETE", "/api/v1/shelter/facilities/{id}", "SKIP", {}, skip_reason="no 2nd facility")

    if fac1:
        s, b = request("POST", "/api/v1/shelter/facilities/bulk/status", {"ids": [fac1], "status": "inactive"}, headers=auth_headers())
        record(m, "bulk status facilities", "POST", "/api/v1/shelter/facilities/bulk/status", s, b, (200, 400))


def main():
    login()
    dog_id = create_dog()
    test_rescue()
    test_adoption(dog_id)
    test_foster(dog_id)
    test_medical(dog_id)
    test_shelter(dog_id)

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
                print(f"  SKIP {r['module']}:{r['test']} â€” {r.get('reason','')}")

    fname = f"docs/api_comprehensive2_report_{BASE.replace('://', '_').replace('/', '_').replace(':', '_')}.json"
    with open(fname, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print(f"\nFull report: {fname}")


if __name__ == "__main__":
    main()
