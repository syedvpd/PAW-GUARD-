import urllib.request
import json
import ssl

BASE_URL = "https://pawguard-backend-mqri.onrender.com"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def test_endpoint(path, method="GET", body=None, token=None):
    url = f"{BASE_URL}{path}"
    req_headers = {"Content-Type": "application/json"}
    if token:
        req_headers["Authorization"] = f"Bearer {token}"
    
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            status = resp.status
            try:
                res_body = json.loads(resp.read().decode("utf-8"))
            except:
                res_body = {}
            return status, res_body
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
        except:
            err_json = err_body
        return e.code, err_json
    except Exception as ex:
        return 0, str(ex)

def main():
    # Login owner to get token
    st, res = test_endpoint("/api/v1/auth/login", method="POST", body={
        "email": "perf_owner_test@example.com",
        "password": "StrongPassword123!"
    })
    token = res.get("data", {}).get("access_token")
    
    endpoints = [
        # Health & Auth
        ("GET", "/health", False),
        ("POST", "/api/v1/auth/login", False),
        ("GET", "/api/v1/auth/me", True),
        
        # Owner / Companion Pet
        ("GET", "/api/v1/companion-pets", True),
        ("GET", "/api/v1/companion-pets/clinics", True),
        ("GET", "/api/v1/companion-pets/appointments", True),
        
        # Dashboards
        ("GET", "/api/v1/dashboards/public", False),
        ("GET", "/api/v1/dashboards/medical", True),
        ("GET", "/api/v1/dashboards/rescue", True),
        ("GET", "/api/v1/dashboards/shelter", True),
        ("GET", "/api/v1/dashboards/adoption", True),
        ("GET", "/api/v1/dashboards/volunteer", True),
        ("GET", "/api/v1/dashboards/finance", True),
        ("GET", "/api/v1/dashboards/executive", True),
        
        # Medical
        ("GET", "/api/v1/medical/exams", True),
        ("GET", "/api/v1/medical/treatments", True),
        ("GET", "/api/v1/medical/vaccinations", True),
        ("GET", "/api/v1/medical/prescriptions", True),
        
        # Admin
        ("GET", "/api/v1/admin/roles", True),
        ("GET", "/api/v1/admin/permissions", True),
        ("GET", "/api/v1/admin/users", True),
        ("GET", "/api/v1/admin/dashboard/summary", True),
        ("GET", "/api/v1/admin/dashboard/metrics", True),
        ("GET", "/api/v1/admin/dashboard/kpis", True),
        ("GET", "/api/v1/admin/audit-logs", True),
        
        # Reports
        ("GET", "/api/v1/reports/types", True),
        ("GET", "/api/v1/reports/formats", True),
    ]

    results = []
    print("Testing 1-VU Baseline Endpoint Inventory...")
    for method, path, needs_auth in endpoints:
        t = token if needs_auth else None
        body = {"email": "perf_owner_test@example.com", "password": "StrongPassword123!"} if path == "/api/v1/auth/login" else None
        st, res_data = test_endpoint(path, method=method, body=body, token=t)
        print(f"{method} {path} -> Status: {st}")
        results.append({
            "method": method,
            "path": path,
            "status": st,
            "needs_auth": needs_auth
        })
        
    with open("performance-tests/data/endpoint_inventory.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
