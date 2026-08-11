"""
Batch 5 API test harness for medium modules:
  - fleet (17 endpoints)
  - inventory (12 endpoints)
  - dashboards (14 endpoints)
"""
import json
import os
import random
import ssl
import string
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE_URL = "http://127.0.0.1:8000/api/v1"
AUTH_PAYLOAD = json.dumps({
    "email": "super.admin@pawguard.com",
    "password": "PawGuard@2026",
}).encode()

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

class ModuleResults:
    def __init__(self, name):
        self.name = name
        self.total = 0
        self.passed = 0
        self.failed = 0

    def record(self, ok):
        self.total += 1
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        return ok

results = {
    "fleet": ModuleResults("FLEET"),
    "inventory": ModuleResults("INVENTORY"),
    "dashboards": ModuleResults("DASHBOARDS"),
}

def rand_suffix(k=5):
    return "".join(random.choices(string.ascii_lowercase, k=k))

class Session:
    def __init__(self):
        self.token = None
        self._login()

    def _login(self):
        req = urllib.request.Request(
            f"{BASE_URL}/auth/login",
            data=AUTH_PAYLOAD,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, context=ssl_context)
        body = json.loads(resp.read())
        token = body.get("data", {}).get("access_token") or body.get("access_token")
        if not token:
            raise RuntimeError(f"Login failed: {body}")
        self.token = token

    def _headers(self, extra=None):
        h = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def do(self, method, path, body=None, raw_response=False, timeout=60, skip_body=False):
        url = f"{BASE_URL}{path}"
        data = None
        headers = self._headers()
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, context=ssl_context, timeout=timeout)
            status = resp.status
            if raw_response or skip_body:
                return status, None, resp
            raw = resp.read()
            try:
                return status, json.loads(raw) if raw else None, None
            except json.JSONDecodeError:
                return status, raw.decode(errors="replace")[:300], None
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode(errors="replace")[:300]
            except Exception:
                pass
            return e.code, body_text, None
        except Exception as e:
            return 0, str(e)[:300], None

    def do_sse(self, path, timeout=5):
        url = f"{BASE_URL}{path}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            resp = urllib.request.urlopen(req, context=ssl_context, timeout=timeout)
            ctype = resp.headers.get("Content-Type", "")
            chunk = resp.read(2048).decode(errors="replace")
            return resp.status, ctype, chunk
        except Exception as e:
            return 0, "", str(e)[:200]


def test(name, module, method, path, expected_statuses, body=None, ok_extra=None, sse=False, timeout=60):
    """
    Run a test. expected_statuses can be an int or list of acceptable statuses.
    ok_extra: optional callable(status, body) -> bool for additional checks.
    """
    module_name = module.upper()
    expected_list = expected_statuses if isinstance(expected_statuses, (list, tuple)) else [expected_statuses]

    if sse:
        status, ctype_hint, chunk = sess.do_sse(path, timeout=timeout)
        ok = status in expected_list and "text/event-stream" in ctype_hint
        if ok:
            print(f"PASS [{module_name}] {name} {method} {path} -> {status} (SSE: {ctype_hint})")
        else:
            print(f"FAIL [{module_name}] {name} {method} {path} -> {status}  ctype={ctype_hint}")
        results[module].record(ok)
        return status, None

    status, body_data, raw_resp = sess.do(method, path, body=body, timeout=timeout)
    ok = status in expected_list
    if body_data is None and 200 <= status < 300:
        ok = True  # 204 etc
    if ok_extra and ok:
        ok = ok_extra(status, body_data)

    if ok:
        print(f"PASS [{module_name}] {name} {method} {path} -> {status}")
        results[module].record(True)
    else:
        body_preview = str(body_data)[:200] if body_data else "(empty)"
        print(f"FAIL [{module_name}] {name} {method} {path} -> {status}")
        print(f"  BODY: {body_preview}")
        results[module].record(False)
    return status, body_data


sess = Session()
print("=" * 70)
print("  PAW-GUARD BATCH 5 API TEST HARNESS")
print("  Modules: fleet (17) | inventory (12) | dashboards (14)")
print("=" * 70)

# ========================
# FLEET (17 endpoints)
# ========================
print("\n--- FLEET MODULE ---")

# 1. POST /fleet/vehicles
plate = f"TEST-{rand_suffix(5).upper()}"
status, vresp = test("create-vehicle", "fleet", "POST", "/fleet/vehicles",
                      [201], body={"make_model": "Ford Transit Test", "license_plate": plate, "vehicle_type": "rescue_van", "mileage": 5000})
vehicle_id = vresp.get("data", {}).get("id") if vresp else None
plate2 = f"TEST-{rand_suffix(5).upper()}"
status2, vresp2 = test("create-vehicle-2", "fleet", "POST", "/fleet/vehicles",
                        [201], body={"make_model": "Chevy Ambulance Test", "license_plate": plate2, "vehicle_type": "ambulance", "mileage": 12000})
vehicle_id2 = vresp2.get("data", {}).get("id") if vresp2 else None

# 2. GET /fleet/vehicles
test("list-vehicles", "fleet", "GET", "/fleet/vehicles", [200])

# 3. GET /fleet/vehicles/{vehicle_id}
if vehicle_id:
    test("get-vehicle", "fleet", "GET", f"/fleet/vehicles/{vehicle_id}", [200])

# 4. PUT /fleet/vehicles/{vehicle_id}
if vehicle_id:
    test("update-vehicle", "fleet", "PUT", f"/fleet/vehicles/{vehicle_id}", [200],
         body={"mileage": 5500})

# 5. PATCH /fleet/vehicles/{vehicle_id}/status
if vehicle_id:
    test("update-vehicle-status", "fleet", "PATCH", f"/fleet/vehicles/{vehicle_id}/status", [200],
         body={"status": "in_maintenance"})
    # Restore
    test("restore-status-active", "fleet", "PATCH", f"/fleet/vehicles/{vehicle_id}/status", [200],
         body={"status": "active"})

# 6. POST /fleet/maintenance
if vehicle_id:
    status_m, mresp = test("log-maintenance", "fleet", "POST", "/fleet/maintenance", [201],
                           body={"vehicle_id": vehicle_id, "service_date": "2026-07-15",
                                 "description": "Oil change test", "cost": 150.0, "next_due_date": "2027-01-15"})

# 7. GET /fleet/vehicles/{vehicle_id}/maintenance
if vehicle_id:
    test("list-maintenance", "fleet", "GET", f"/fleet/vehicles/{vehicle_id}/maintenance", [200])

# 8. POST /fleet/equipment
if vehicle_id:
    status_e, eresp = test("checkout-equipment", "fleet", "POST", "/fleet/equipment", [201],
                           body={"equipment_name": f"Net Gun {rand_suffix(3)}",
                                 "assigned_to_vehicle_id": vehicle_id,
                                 "notes": "Test equipment checkout"})
    equip_id = eresp.get("data", {}).get("id") if eresp else None
    status_e2, eresp2 = test("checkout-equipment-agent", "fleet", "POST", "/fleet/equipment", [201],
                        body={"equipment_name": f"Radio {rand_suffix(3)}",
                              "notes": "Agent-only equipment"})
    equip_id2 = eresp2.get("data", {}).get("id") if eresp2 else None
else:
    status_e, eresp = None, None
    status_e2, eresp2 = None, None

# 9. GET /fleet/equipment
test("list-equipment", "fleet", "GET", "/fleet/equipment", [200])

# 10. GET /fleet/equipment/{checkout_id}
if equip_id:
    test("get-equipment", "fleet", "GET", f"/fleet/equipment/{equip_id}", [200])

# 11. POST /fleet/equipment/{checkout_id}/return
if equip_id:
    test("return-equipment", "fleet", "POST", f"/fleet/equipment/{equip_id}/return", [200],
         body={"notes": "Returned in good condition"})

# 12. POST /fleet/vehicles/{vehicle_id}/fuel
if vehicle_id:
    status_fu, furesp = test("log-fuel", "fleet", "POST", f"/fleet/vehicles/{vehicle_id}/fuel", [201],
                             body={"fuel_type": "Diesel", "volume_litres": 45.5, "cost": 68.25,
                                   "mileage_at_fill": 5500, "vendor": "Shell Test"})
    fuel_log_id = furesp.get("data", {}).get("id") if furesp else None
else:
    fuel_log_id = None

# 13. GET /fleet/vehicles/{vehicle_id}/fuel
if vehicle_id:
    test("list-fuel-logs", "fleet", "GET", f"/fleet/vehicles/{vehicle_id}/fuel", [200])

# 14. GET /fleet/fuel/{log_id}
if fuel_log_id:
    test("get-fuel-log", "fleet", "GET", f"/fleet/fuel/{fuel_log_id}", [200])

# 15. POST /fleet/bulk/status-update
if vehicle_id and vehicle_id2:
    test("bulk-status-update", "fleet", "POST", "/fleet/bulk/status-update", [200],
         body={"ids": [vehicle_id, vehicle_id2], "status": "out_of_service"})
    # Restore
    test("bulk-status-restore", "fleet", "POST", "/fleet/bulk/status-update", [200],
         body={"ids": [vehicle_id, vehicle_id2], "status": "active"})

# 16. POST /fleet/bulk/delete
if vehicle_id and vehicle_id2:
    test("bulk-delete", "fleet", "POST", "/fleet/bulk/delete", [200],
         body={"ids": [vehicle_id, vehicle_id2]})

# 17. DELETE /fleet/vehicles/{vehicle_id}
# Use a fresh vehicle for this since we already bulk-deleted them
plate_del = f"DEL-{rand_suffix(5).upper()}"
sd, vdresp = test("create-for-delete", "fleet", "POST", "/fleet/vehicles", [201],
                  body={"make_model": "Delete Me", "license_plate": plate_del, "vehicle_type": "utility", "mileage": 1000})
del_vid = vdresp.get("data", {}).get("id") if vdresp else None
if del_vid:
    test("soft-delete-vehicle", "fleet", "DELETE", f"/fleet/vehicles/{del_vid}", [200])


# ========================
# INVENTORY (12 endpoints)
# ========================
print("\n--- INVENTORY MODULE ---")

# 1. POST /inventory/items
item_name = f"TestVaccine_{rand_suffix(4)}"
status_i, iresp = test("create-item", "inventory", "POST", "/inventory/items", [201],
                       body={"name": item_name, "category": "vaccine", "quantity": 50.0,
                             "unit": "vial", "reorder_threshold": 10.0, "unit_cost": 4.50})
item_id = iresp.get("data", {}).get("id") if iresp else None

item_name2 = f"TestBandage_{rand_suffix(4)}"
status_i2, iresp2 = test("create-item-2", "inventory", "POST", "/inventory/items", [201],
                         body={"name": item_name2, "category": "consumable", "quantity": 200.0,
                               "unit": "piece", "reorder_threshold": 50.0, "unit_cost": 0.25})
item_id2 = iresp2.get("data", {}).get("id") if iresp2 else None

# 2. GET /inventory/items
test("list-items", "inventory", "GET", "/inventory/items", [200])

# 3. GET /inventory/items/{item_id}
if item_id:
    test("get-item", "inventory", "GET", f"/inventory/items/{item_id}", [200])

# 4. POST /inventory/movements
if item_id:
    status_mv, mvresp = test("record-movement", "inventory", "POST", "/inventory/movements", [201],
                             body={"item_id": item_id, "movement_type": "check_in", "quantity": 10.0,
                                   "notes": "Test movement"})

# 5. GET /inventory/items/{item_id}/movements
if item_id:
    test("list-movements", "inventory", "GET", f"/inventory/items/{item_id}/movements", [200])

# 6. POST /inventory/requisitions
if item_id:
    status_r, rresp = test("create-requisition", "inventory", "POST", "/inventory/requisitions", [201],
                           body={"item_id": item_id, "quantity": 100.0})
    req_id = rresp.get("data", {}).get("id") if rresp else None
else:
    req_id = None

# 7. GET /inventory/requisitions
test("list-requisitions", "inventory", "GET", "/inventory/requisitions", [200])

# 8. PUT /inventory/requisitions/{req_id}/status
if req_id:
    test("update-requisition-status", "inventory", "PUT", f"/inventory/requisitions/{req_id}/status", [200],
         body={"status": "approved"})

# 9. DELETE /inventory/items/{item_id}
item_name_del = f"TestDel_{rand_suffix(4)}"
sd2, idresp = test("create-for-del", "inventory", "POST", "/inventory/items", [201],
                   body={"name": item_name_del, "category": "office", "quantity": 5.0,
                         "unit": "box", "reorder_threshold": 2.0, "unit_cost": 3.0})
del_item_id = idresp.get("data", {}).get("id") if idresp else None
if del_item_id:
    test("delete-item", "inventory", "DELETE", f"/inventory/items/{del_item_id}", [200])

# 10. DELETE /admin/inventory/items/{item_id}  (admin path variant)
item_name_adm = f"TestAdm_{rand_suffix(4)}"
sda, admresp = test("create-for-admin-del", "inventory", "POST", "/inventory/items", [201],
                    body={"name": item_name_adm, "category": "gear", "quantity": 3.0,
                          "unit": "pair", "reorder_threshold": 1.0, "unit_cost": 15.0})
adm_item_id = admresp.get("data", {}).get("id") if admresp else None
if adm_item_id:
    test("admin-delete-item", "inventory", "DELETE", f"/admin/inventory/items/{adm_item_id}", [200])

# 11. POST /inventory/items/bulk/delete
if item_id and item_id2:
    test("bulk-delete-items", "inventory", "POST", "/inventory/items/bulk/delete", [200],
         body={"ids": [item_id, item_id2]})

# 12. POST /inventory/requisitions/bulk/status
if req_id:
    # Create another requisition so we have 2 IDs
    item_name_r2 = f"TestReq2_{rand_suffix(4)}"
    s3, r3resp = test("create-item-for-req2", "inventory", "POST", "/inventory/items", [201],
                      body={"name": item_name_r2, "category": "food", "quantity": 500.0,
                            "unit": "kg", "reorder_threshold": 100.0, "unit_cost": 2.0})
    r3_item_id = r3resp.get("data", {}).get("id") if r3resp else None
    if r3_item_id:
        sr2, r2resp = test("create-requisition-2", "inventory", "POST", "/inventory/requisitions", [201],
                           body={"item_id": r3_item_id, "quantity": 50.0})
        req_id2 = r2resp.get("data", {}).get("id") if r2resp else None
        if req_id and req_id2:
            test("bulk-update-requisitions", "inventory", "POST", "/inventory/requisitions/bulk/status", [200],
                 body={"ids": [req_id, req_id2], "status": "approved"})


# ========================
# DASHBOARDS (14 endpoints)
# ========================
print("\n--- DASHBOARDS MODULE ---")

dashboards = [
    ("rescue-dashboard", "/dashboards/rescue"),
    ("shelter-dashboard", "/dashboards/shelter"),
    ("medical-dashboard", "/dashboards/medical"),
    ("adoption-dashboard", "/dashboards/adoption"),
    ("foster-dashboard", "/dashboards/foster"),
    ("volunteer-dashboard", "/dashboards/volunteer"),
    ("inventory-dashboard", "/dashboards/inventory"),
    ("finance-dashboard", "/dashboards/finance"),
    ("donor-dashboard", "/dashboards/donor"),
    ("staff-dashboard", "/dashboards/staff"),
    ("executive-dashboard", "/dashboards/executive"),
    ("public-dashboard", "/dashboards/public"),
    ("operations-dashboard", "/dashboards/operations"),
]

for name, path in dashboards:
    test(name, "dashboards", "GET", path, [200])

# 14. GET /dashboards/rescue/stream (SSE)
print("\n--- SSE Stream Test ---")
test("rescue-stream-sse", "dashboards", "GET", "/dashboards/rescue/stream?interval=10", [200], sse=True, timeout=15)


# ========================
# SUMMARY
# ========================
print("\n" + "=" * 70)
print("  BATCH 5 TEST SUMMARY")
print("=" * 70)
grand_total = 0
grand_passed = 0
for key in ["fleet", "inventory", "dashboards"]:
    r = results[key]
    grand_total += r.total
    grand_passed += r.passed
    status_icon = "OK" if r.failed == 0 else "XX"
    print(f"  {key.upper():12s}: {r.passed:2d}/{r.total:2d} passed  [{status_icon}]")
print(f"  {'TOTAL':12s}: {grand_passed:2d}/{grand_total:2d} passed")
print("=" * 70)

sys.exit(0 if grand_total == grand_passed else 1)
