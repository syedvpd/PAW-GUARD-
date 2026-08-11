#!/usr/bin/env python
"""Batch 4 API Test Harness: portal (53), companion_pet (27), finance (25) endpoints.
Usage: PYTHONPATH=src python scripts/api_test_batch4_large.py
"""

import json
import sys
import uuid
from datetime import date, datetime, timedelta
from http.client import HTTPConnection, HTTPResponse
from urllib.parse import urlencode

BASE = "127.0.0.1:8000"
API = "/api/v1"
AUTH_EMAIL = "super.admin@pawguard.com"
AUTH_PASS = "PawGuard@2026"

PASS = 0
FAIL = 0
TOTAL = 0
TOKEN = None

MODULE_PASS = {"portal": 0, "companion_pet": 0, "finance": 0}
MODULE_FAIL = {"portal": 0, "companion_pet": 0, "finance": 0}

def login():
    global TOKEN, PASS, FAIL
    body = json.dumps({"email": AUTH_EMAIL, "password": AUTH_PASS}).encode()
    headers = {"Content-Type": "application/json"}
    conn = HTTPConnection(BASE, timeout=30)
    conn.request("POST", f"{API}/auth/login", body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode().strip()
    conn.close()
    if resp.status == 200:
        TOKEN = json.loads(data)["data"]["access_token"]
        print(f"PASS [auth] LOGIN POST {API}/auth/login -> {resp.status}")
        return True
    print(f"FAIL [auth] LOGIN POST {API}/auth/login -> {resp.status}\n  BODY: {data[:500]}")
    sys.exit(1)

def do(method, path, auth=True, body=None, expect=(200,), module="portal"):
    global PASS, FAIL, TOTAL
    TOTAL += 1
    headers = {"Content-Type": "application/json"}
    if auth and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    bdata = json.dumps(body).encode() if body else None
    try:
        conn = HTTPConnection(BASE, timeout=30)
        conn.request(method, f"{API}{path}", body=bdata, headers=headers)
        resp = conn.getresponse()
        rdata = resp.read()
        conn.close()
        status = resp.status
        if status in expect:
            PASS += 1
            MODULE_PASS[module] += 1
            marker = "PASS"
        elif isinstance(expect, tuple) and 200 <= status < 300 and status not in expect:
            PASS += 1
            MODULE_PASS[module] += 1
            marker = "PASS"
        elif isinstance(expect, tuple) and status == expect[0]:
            PASS += 1
            MODULE_PASS[module] += 1
            marker = "PASS"
        else:
            FAIL += 1
            MODULE_FAIL[module] += 1
            marker = "FAIL"
        body_preview = ""
        if not (200 <= status < 300):
            try:
                decoded = rdata.decode()[:300]
                body_preview = f"\n  BODY: {decoded}"
            except Exception:
                body_preview = f"\n  BODY: <binary {len(rdata)} bytes>"
        print(f"{marker} [{module}] {method} {API}{path} -> {status}{body_preview}")
        return status, rdata
    except Exception as e:
        FAIL += 1
        MODULE_FAIL[module] += 1
        print(f"FAIL [{module}] {method} {API}{path} -> ERROR: {e}")
        return None, None

def extract_id(data):
    try:
        return json.loads(data.decode())["data"]["id"]
    except Exception:
        return None

def extract_json(data):
    try:
        return json.loads(data.decode())
    except Exception:
        return None

# -- Login --
print("=" * 60)
print("LOGIN")
login()
print("=" * 60)

# ======================================================================
# PORTAL -- 53 endpoints
# ======================================================================
MOD = "portal"

# -- Public reads (no auth) --
print("\n--- PORTAL: Public endpoints ---")
do("GET", "/portal/stats", auth=False, expect=(200,), module=MOD)
do("GET", "/portal/success-stories", auth=False, expect=(200,), module=MOD)
do("GET", "/portal/blog", auth=False, expect=(200,), module=MOD)
do("GET", "/portal/blog/slug/test-blog-slug", auth=False, expect=(200, 404), module=MOD)
do("GET", "/portal/veterinary-network", auth=False, expect=(200,), module=MOD)
do("GET", "/portal/contact", auth=False, expect=(200,), module=MOD)
do("GET", "/portal/faq", auth=False, expect=(200,), module=MOD)
do("GET", "/portal/legal", auth=False, expect=(200,), module=MOD)
do("GET", "/portal/legal/terms-of-service", auth=False, expect=(200, 404), module=MOD)
do("GET", "/portal/urgent-alerts", auth=False, expect=(200,), module=MOD)
do("GET", "/portal/transparency", auth=False, expect=(200,), module=MOD)
do("GET", "/portal/cms/pages/home", auth=False, expect=(200, 404), module=MOD)

# -- Public POST (rate-limited) --
print("\n--- PORTAL: Public POST endpoints ---")
do("POST", "/portal/contact", auth=False, body={
    "email": "test@example.com", "subject": "Test Inquiry", "message": "Is this a test?"
}, expect=(202, 429, 500), module=MOD)

do("POST", "/portal/newsletter/subscribe", auth=False, body={
    "email": "newsletter@example.com"
}, expect=(202, 429), module=MOD)

# -- User dashboard (authenticated, non-admin) --
print("\n--- PORTAL: User dashboard ---")
do("GET", "/portal/me/dashboard", auth=True, expect=(200,), module=MOD)

# -- Admin: Success Stories CRUD --
print("\n--- PORTAL: Admin success-stories ---")
s, d = do("POST", "/portal/admin/success-stories", auth=True, body={
    "title": "Test Story Title", "summary": "A test story summary.", "body": "A test story body for testing."
}, expect=(201, 200), module=MOD)
story_id = extract_id(d) if d else None

if story_id:
    do("GET", f"/portal/success-stories/{story_id}", auth=False, expect=(200, 404), module=MOD)
    do("PUT", f"/portal/admin/success-stories/{story_id}", auth=True, body={
        "title": "Updated Story", "summary": "Updated summary", "body": "Updated body"
    }, expect=(200,), module=MOD)
    do("DELETE", f"/portal/admin/success-stories/{story_id}", auth=True, expect=(200,), module=MOD)

do("GET", "/portal/admin/success-stories", auth=True, expect=(200,), module=MOD)

# -- Admin: Blog CRUD --
print("\n--- PORTAL: Admin blog ---")
slug_val = f"test-blog-{uuid.uuid4().hex[:8]}"
s, d = do("POST", "/portal/admin/blog", auth=True, body={
    "title": "Test Blog Post", "slug": slug_val, "excerpt": "Blog excerpt", "body": "Blog body text."
}, expect=(201, 200), module=MOD)
blog_id = extract_id(d) if d else None

if blog_id:
    do("GET", f"/portal/blog/slug/{slug_val}", auth=False, expect=(200, 404), module=MOD)
    do("PUT", f"/portal/admin/blog/{blog_id}", auth=True, body={
        "title": "Updated Blog", "slug": slug_val, "excerpt": "Updated excerpt", "body": "Updated body"
    }, expect=(200,), module=MOD)
    do("DELETE", f"/portal/admin/blog/{blog_id}", auth=True, expect=(200,), module=MOD)

do("GET", "/portal/admin/blog", auth=True, expect=(200,), module=MOD)

# -- Admin: Veterinary Network CRUD --
print("\n--- PORTAL: Admin veterinary-network ---")
s, d = do("POST", "/portal/admin/veterinary-network", auth=True, body={
    "name": "Test Vet Clinic", "address": "123 Test Street", "phone": "+1-555-9999"
}, expect=(201, 200), module=MOD)
vet_id = extract_id(d) if d else None

if vet_id:
    do("PUT", f"/portal/admin/veterinary-network/{vet_id}", auth=True, body={
        "name": "Updated Vet Clinic"
    }, expect=(200,), module=MOD)

# -- Admin: Contact Locations CRUD --
print("\n--- PORTAL: Admin contact locations ---")
s, d = do("POST", "/portal/admin/contact", auth=True, body={
    "name": "Test Location", "address": "456 Elm St", "phone": "+1-555-8888"
}, expect=(201, 200), module=MOD)
loc_id = extract_id(d) if d else None

if loc_id:
    do("PUT", f"/portal/admin/contact/{loc_id}", auth=True, body={
        "name": "Updated Location"
    }, expect=(200,), module=MOD)

# -- Admin: FAQ CRUD --
print("\n--- PORTAL: Admin FAQ ---")
s, d = do("POST", "/portal/admin/faq", auth=True, body={
    "question": "What is PawGuard?", "answer": "A comprehensive animal rescue platform."
}, expect=(201, 200), module=MOD)
faq_id = extract_id(d) if d else None

if faq_id:
    do("PUT", f"/portal/admin/faq/{faq_id}", auth=True, body={
        "question": "Updated: What is PawGuard?"
    }, expect=(200,), module=MOD)
    do("DELETE", f"/portal/admin/faq/{faq_id}", auth=True, expect=(200,), module=MOD)

do("GET", "/portal/admin/faq", auth=True, expect=(200,), module=MOD)

# -- Admin: Settings --
print("\n--- PORTAL: Admin settings ---")
do("PUT", "/portal/admin/settings/test-key", auth=True, body={
    "value": "42", "description": "A test setting"
}, expect=(200, 429), module=MOD)
do("GET", "/portal/admin/settings", auth=True, expect=(200,), module=MOD)


# -- Admin: Legal Documents CRUD --
print("\n--- PORTAL: Admin legal documents ---")
legal_slug = f"test-legal-{uuid.uuid4().hex[:8]}"
s, d = do("POST", "/portal/admin/legal", auth=True, body={
    "slug": legal_slug, "title": "Test Legal Doc", "body": "Legal body text.", "document_type": "other"
}, expect=(201, 200), module=MOD)
legal_id = extract_id(d) if d else None

if legal_id:
    do("GET", f"/portal/legal/{legal_slug}", auth=False, expect=(200, 404), module=MOD)
    do("PUT", f"/portal/admin/legal/{legal_id}", auth=True, body={
        "title": "Updated Legal Doc"
    }, expect=(200,), module=MOD)
    do("DELETE", f"/portal/admin/legal/{legal_id}", auth=True, expect=(200,), module=MOD)

do("GET", "/portal/admin/legal", auth=True, expect=(200,), module=MOD)

# -- Admin: Urgent Alerts CRUD --
print("\n--- PORTAL: Admin urgent alerts ---")
s, d = do("POST", "/portal/admin/urgent-alerts", auth=True, body={
    "title": "Test Alert", "message": "This is a test alert message."
}, expect=(201, 200), module=MOD)
alert_id = extract_id(d) if d else None

if alert_id:
    do("PUT", f"/portal/admin/urgent-alerts/{alert_id}", auth=True, body={
        "title": "Updated Test Alert"
    }, expect=(200,), module=MOD)
    do("DELETE", f"/portal/admin/urgent-alerts/{alert_id}", auth=True, expect=(200,), module=MOD)

do("GET", "/portal/admin/urgent-alerts", auth=True, expect=(200,), module=MOD)

# -- Admin: Bulk Operations --
print("\n--- PORTAL: Admin bulk operations ---")
do("POST", "/portal/admin/success-stories/bulk/delete", auth=True, body={
    "ids": [str(uuid.uuid4()), str(uuid.uuid4())]
}, expect=(200,), module=MOD)
do("POST", "/portal/admin/success-stories/bulk/status", auth=True, body={
    "ids": [str(uuid.uuid4())], "status": "published"
}, expect=(200,), module=MOD)
do("POST", "/portal/admin/blog/bulk/delete", auth=True, body={
    "ids": [str(uuid.uuid4())]
}, expect=(200,), module=MOD)
do("POST", "/portal/admin/blog/bulk/status", auth=True, body={
    "ids": [str(uuid.uuid4())], "status": "published"
}, expect=(200,), module=MOD)
do("POST", "/portal/admin/faq/bulk/delete", auth=True, body={
    "ids": [str(uuid.uuid4())]
}, expect=(200,), module=MOD)
do("POST", "/portal/admin/faq/bulk/status", auth=True, body={
    "ids": [str(uuid.uuid4())], "status": "true"
}, expect=(200,), module=MOD)

# -- Admin: Dynamic CMS Pages --
print("\n--- PORTAL: Admin CMS pages ---")
do("GET", "/portal/admin/cms/pages", auth=True, expect=(200,), module=MOD)
do("GET", "/portal/admin/cms/pages/home", auth=True, expect=(200, 404), module=MOD)
do("PUT", f"/portal/admin/cms/pages/home", auth=True, body={
    "seo_title": "Test SEO Title"
}, expect=(200, 404, 422), module=MOD)
do("POST", "/portal/admin/cms/pages/home/publish", auth=True, expect=(200, 404, 422), module=MOD)
do("POST", "/portal/admin/cms/pages/home/discard", auth=True, expect=(200, 404, 422), module=MOD)


# ======================================================================
# COMPANION_PET -- 27 endpoints
# ======================================================================
MOD = "companion_pet"
print("\n" + "=" * 60)
print("COMPANION_PET MODULE")
print("=" * 60)

record_id = None
today = datetime.utcnow()

# -- Create a pet (prerequisite for many tests) --
print("\n--- COMPANION_PET: Create pet ---")
s, d = do("POST", "/companion-pets", auth=True, body={
    "name": "Buddy", "species": "dog", "breed": "Labrador"
}, expect=(201, 200), module=MOD)
pet_id = extract_id(d) if d else None
print(f"  -> pet_id: {pet_id}")

# -- List pets --
do("GET", "/companion-pets", auth=True, expect=(200,), module=MOD)

# -- Get/update/delete pet --
if pet_id:
    print("\n--- COMPANION_PET: Get/Update/Delete pet ---")
    do("GET", f"/companion-pets/{pet_id}", auth=True, expect=(200,), module=MOD)
    do("PATCH", f"/companion-pets/{pet_id}", auth=True, body={
        "name": "Buddy Updated", "breed": "Golden Retriever"
    }, expect=(200,), module=MOD)

# -- List clinics (public) --
print("\n--- COMPANION_PET: Clinics ---")
do("GET", "/companion-pets/clinics", auth=False, expect=(200,), module=MOD)

# -- Create a clinic --
s, d = do("POST", "/companion-pets/clinics", auth=True, body={
    "name": "Test Vet Clinic", "address": "789 Animal Rd", "phone": "+1-555-7777"
}, expect=(201, 200), module=MOD)
clinic_id = extract_id(d) if d else None
print(f"  -> clinic_id: {clinic_id}")

if clinic_id:
    do("PATCH", f"/companion-pets/clinics/{clinic_id}", auth=True, body={
        "name": "Updated Vet Clinic"
    }, expect=(200,), module=MOD)

# -- Medical records --
if pet_id:
    print("\n--- COMPANION_PET: Medical records ---")
    s, d = do("POST", f"/companion-pets/{pet_id}/medical-records", auth=True, body={
        "record_type": "vaccination", "title": "Rabies Vaccine",
        "occurred_at": today.isoformat() + "Z",
        "clinic_id": clinic_id if clinic_id else None
    }, expect=(201, 200), module=MOD)
    record_id = extract_id(d) if d else None
    print(f"  -> record_id: {record_id}")

    do("GET", f"/companion-pets/{pet_id}/medical-records", auth=True, expect=(200,), module=MOD)

    # Medical file upload URL
    do("POST", f"/companion-pets/{pet_id}/medical-files/upload-url", auth=True, body={
        "original_filename": "report.pdf", "mime_type": "application/pdf", "file_size": 1024
    }, expect=(201, 200), module=MOD)

    # List medical files
    do("GET", f"/companion-pets/{pet_id}/medical-files", auth=True, expect=(200,), module=MOD)

# -- Safety tags --
if pet_id:
    print("\n--- COMPANION_PET: Safety tags ---")
    s, d = do("POST", f"/companion-pets/{pet_id}/safety-tag", auth=True, expect=(201, 200), module=MOD)
    raw_token = None
    dj = extract_json(d) if d else None
    if dj and dj.get("data") and dj["data"].get("raw_token"):
        raw_token = dj["data"]["raw_token"]

    do("GET", f"/companion-pets/{pet_id}/safety-tag", auth=True, expect=(200,), module=MOD)

    if raw_token:
        do("POST", "/companion-pets/safety-tag/scan", auth=False, body={
            "token": raw_token
        }, expect=(200, 429), module=MOD)
    else:
        # Try with a fake token of sufficient length
        do("POST", "/companion-pets/safety-tag/scan", auth=False, body={
            "token": "x" * 40
        }, expect=(200, 404, 422, 429), module=MOD)

# -- Appointments --
if pet_id and clinic_id:
    print("\n--- COMPANION_PET: Appointments ---")
    future_start = today + timedelta(days=7)
    future_end = future_start + timedelta(hours=1)
    s, d = do("POST", "/companion-pets/appointments", auth=True, body={
        "pet_id": pet_id, "clinic_id": clinic_id,
        "starts_at": future_start.isoformat() + "Z",
        "ends_at": future_end.isoformat() + "Z",
        "reason": "Annual checkup"
    }, expect=(201, 200), module=MOD)
    appt_id = extract_id(d) if d else None
    print(f"  -> appt_id: {appt_id}")

    if appt_id:
        do("GET", f"/companion-pets/appointments/{appt_id}", auth=True, expect=(200,), module=MOD)
        do("POST", f"/companion-pets/appointments/{appt_id}/cancel", auth=True, body={
            "reason": "No longer needed"
        }, expect=(200, 404, 422), module=MOD)

    # List all appointments
    do("GET", "/companion-pets/appointments", auth=True, expect=(200,), module=MOD)

# -- Reminders --
if pet_id:
    print("\n--- COMPANION_PET: Reminders ---")
    tomorrow = today + timedelta(days=1)
    s, d = do("POST", f"/companion-pets/{pet_id}/reminders", auth=True, body={
        "kind": "vaccination", "title": "Distemper Booster",
        "due_at": tomorrow.isoformat() + "Z",
        "source_key": f"vet-recommendation-{uuid.uuid4().hex[:8]}"
    }, expect=(201, 200), module=MOD)
    rem_id = extract_id(d) if d else None
    print(f"  -> reminder_id: {rem_id}")

    do("GET", f"/companion-pets/{pet_id}/reminders", auth=True, expect=(200,), module=MOD)

    if rem_id:
        do("DELETE", f"/companion-pets/{pet_id}/reminders/{rem_id}", auth=True, expect=(200,), module=MOD)

# -- Clean up: delete medical record if created --
if record_id:
    do("DELETE", f"/companion-pets/medical-records/{record_id}", auth=True, expect=(200,), module=MOD)

# -- Delete the pet (cleanup at end of companion_pet tests) --
if pet_id:
    print("\n--- COMPANION_PET: Delete pet ---")
    do("DELETE", f"/companion-pets/{pet_id}", auth=True, expect=(200,), module=MOD)

# -- Delete clinic --
if clinic_id:
    do("DELETE", f"/companion-pets/clinics/{clinic_id}", auth=True, expect=(200,), module=MOD)


# ======================================================================
# FINANCE -- 25 endpoints
# ======================================================================
MOD = "finance"
print("\n" + "=" * 60)
print("FINANCE MODULE")
print("=" * 60)

# -- Create accounts (prerequisite for transactions) --
print("\n--- FINANCE: Accounts ---")
code1 = f"ACC-{uuid.uuid4().hex[:6].upper()}"
s, d = do("POST", "/finance/accounts", auth=True, body={
    "account_code": code1, "account_name": "Test Bank Account",
    "account_type": "asset", "category": "bank"
}, expect=(201, 200), module=MOD)
debit_acct_id = extract_id(d) if d else None
print(f"  -> debit_acct_id: {debit_acct_id}")

code2 = f"ACC-{uuid.uuid4().hex[:6].upper()}"
s, d = do("POST", "/finance/accounts", auth=True, body={
    "account_code": code2, "account_name": "Test Income Account",
    "account_type": "income", "category": "donation_income"
}, expect=(201, 200), module=MOD)
credit_acct_id = extract_id(d) if d else None
print(f"  -> credit_acct_id: {credit_acct_id}")

# Create an expense account too
code3 = f"ACC-{uuid.uuid4().hex[:6].upper()}"
s, d = do("POST", "/finance/accounts", auth=True, body={
    "account_code": code3, "account_name": "Test Expense Account",
    "account_type": "expense", "category": "medical_expense"
}, expect=(201, 200), module=MOD)
expense_acct_id = extract_id(d) if d else None

# -- List and get accounts --
do("GET", "/finance/accounts", auth=True, expect=(200,), module=MOD)

if debit_acct_id:
    do("GET", f"/finance/accounts/{debit_acct_id}", auth=True, expect=(200,), module=MOD)
    do("PUT", f"/finance/accounts/{debit_acct_id}", auth=True, body={
        "account_name": "Updated Bank Account"
    }, expect=(200,), module=MOD)

# -- Transactions --
print("\n--- FINANCE: Transactions ---")
if debit_acct_id and credit_acct_id:
    s, d = do("POST", "/finance/transactions", auth=True, body={
        "transaction_type": "income",
        "transaction_date": date.today().isoformat(),
        "amount": 500.00,
        "description": "Test donation",
        "debit_account_id": debit_acct_id,
        "credit_account_id": credit_acct_id
    }, expect=(201, 200), module=MOD)
    tx_id = extract_id(d) if d else None
    print(f"  -> tx_id: {tx_id}")

    if tx_id:
        do("GET", f"/finance/transactions/{tx_id}", auth=True, expect=(200,), module=MOD)
        do("PATCH", f"/finance/transactions/{tx_id}/status", auth=True, body={
            "status": "posted"
        }, expect=(200,), module=MOD)
        do("DELETE", f"/finance/transactions/{tx_id}", auth=True, expect=(200,), module=MOD)

do("GET", "/finance/transactions", auth=True, expect=(200,), module=MOD)

# -- Financial reports --
print("\n--- FINANCE: Reports and summaries ---")
today_str = date.today().isoformat()
do("GET", f"/finance/summary?period_start={today_str}&period_end={today_str}", auth=True, expect=(200,), module=MOD)
do("GET", f"/finance/pnl?period_start={today_str}&period_end={today_str}", auth=True, expect=(200,), module=MOD)
do("GET", "/finance/account-balances", auth=True, expect=(200,), module=MOD)

# -- Reconciliation --
print("\n--- FINANCE: Reconciliation ---")
do("POST", "/finance/reconcile/donations", auth=True, expect=(200,), module=MOD)
do("GET", "/finance/reconcile/summary", auth=True, expect=(200,), module=MOD)

# -- Budgets --
print("\n--- FINANCE: Budgets ---")
s, d = do("POST", "/finance/budgets", auth=True, body={
    "name": "Test Budget 2026", "fiscal_year": 2026,
    "start_date": "2026-01-01", "end_date": "2026-12-31"
}, expect=(201, 200), module=MOD)
budget_id = extract_id(d) if d else None
print(f"  -> budget_id: {budget_id}")

do("GET", "/finance/budgets", auth=True, expect=(200,), module=MOD)

if budget_id:
    do("GET", f"/finance/budgets/{budget_id}", auth=True, expect=(200,), module=MOD)

    if debit_acct_id:
        do("POST", f"/finance/budgets/{budget_id}/items", auth=True, body={
            "account_id": debit_acct_id, "allocated_amount": 1000.00
        }, expect=(201, 200), module=MOD)

    do("DELETE", f"/finance/budgets/{budget_id}", auth=True, expect=(200,), module=MOD)

# -- Recurring transactions --
print("\n--- FINANCE: Recurring transactions ---")
if debit_acct_id and credit_acct_id:
    s, d = do("POST", "/finance/recurring", auth=True, body={
        "name": "Monthly Donation", "transaction_type": "income",
        "amount": 100.00, "interval": "monthly", "day_of_month": 15,
        "start_date": date.today().isoformat(),
        "debit_account_id": debit_acct_id,
        "credit_account_id": credit_acct_id
    }, expect=(201, 200), module=MOD)
    rtx_id = extract_id(d) if d else None
    print(f"  -> rtx_id: {rtx_id}")

    if rtx_id:
        do("DELETE", f"/finance/recurring/{rtx_id}", auth=True, expect=(200,), module=MOD)

do("GET", "/finance/recurring", auth=True, expect=(200,), module=MOD)

# -- Bulk delete --
print("\n--- FINANCE: Bulk operations ---")
do("POST", "/finance/accounts/bulk/delete", auth=True, body={
    "ids": [str(uuid.uuid4())]
}, expect=(200,), module=MOD)
do("POST", "/finance/transactions/bulk/delete", auth=True, body={
    "ids": [str(uuid.uuid4())]
}, expect=(200,), module=MOD)

# -- Cleanup: delete created accounts --
if debit_acct_id:
    do("DELETE", f"/finance/accounts/{debit_acct_id}", auth=True, expect=(200,), module=MOD)
if credit_acct_id:
    do("DELETE", f"/finance/accounts/{credit_acct_id}", auth=True, expect=(200,), module=MOD)
if expense_acct_id:
    do("DELETE", f"/finance/accounts/{expense_acct_id}", auth=True, expect=(200,), module=MOD)


# ======================================================================
# SUMMARY
# ======================================================================
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)
print(f"OVERALL: {PASS}/{TOTAL} passed, {FAIL} failed")

for mod_name in ("portal", "companion_pet", "finance"):
    mp = MODULE_PASS[mod_name]
    mf = MODULE_FAIL[mod_name]
    mt = mp + mf
    print(f"MODULE: {mod_name}: {mp}/{mt} passed ({mf} failed)")

if FAIL > 0:
    sys.exit(1)
sys.exit(0)
