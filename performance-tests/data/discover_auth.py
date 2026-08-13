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
            res_body = json.loads(resp.read().decode("utf-8"))
            return status, res_body
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
        except:
            err_json = err_body
        return e.code, err_json

def get_token(email, password, name):
    # Try register first
    test_endpoint("/api/v1/auth/register", method="POST", body={
        "email": email,
        "password": password,
        "full_name": name,
        "phone": "+1234567890"
    })
    st, res = test_endpoint("/api/v1/auth/login", method="POST", body={
        "email": email,
        "password": password
    })
    if st == 200 and "access_token" in res.get("data", {}):
        return res["data"]["access_token"]
    return None

def main():
    print("Testing Vet Clinic Role...")
    vet_token = get_token("perf_vet_test@example.com", "StrongPassword123!", "Perf Vet")
    if vet_token:
        print("Vet logged in.")
        st, res = test_endpoint("/api/v1/companion-pets/clinics", token=vet_token)
        print("GET /companion-pets/clinics:", st)
        clinics = res.get("data", [])
        if clinics:
            cid = clinics[0]["id"]
            st, res = test_endpoint(f"/api/v1/companion-pets/clinics/{cid}/vets", token=vet_token)
            print(f"GET /companion-pets/clinics/{cid}/vets:", st)
            st, res = test_endpoint(f"/api/v1/companion-pets/clinics/{cid}/appointments", token=vet_token)
            print(f"GET /companion-pets/clinics/{cid}/appointments:", st)

    print("\nTesting Admin Role...")
    admin_token = get_token("perf_admin_test@example.com", "StrongPassword123!", "Perf Admin")
    if admin_token:
        print("Admin logged in.")
        st, res = test_endpoint("/api/v1/dashboards/overview", token=admin_token)
        print("GET /dashboards/overview:", st)
        st, res = test_endpoint("/api/v1/reports/summary", token=admin_token)
        print("GET /reports/summary:", st)
        st, res = test_endpoint("/api/v1/companion-pets", token=admin_token)
        print("GET /companion-pets (admin):", st)

if __name__ == "__main__":
    main()
