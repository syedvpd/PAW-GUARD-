import urllib.request
import json
import ssl

BASE_URL = "https://pawguard-backend-mqri.onrender.com"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def test_login(email, password):
    url = f"{BASE_URL}/api/v1/auth/login"
    req_headers = {"Content-Type": "application/json"}
    data = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err)
        except:
            return e.code, err

def main():
    test_emails = [
        "admin@test.com",
        "admin@pawguard.org",
        "vet@test.com",
        "clinic@test.com",
        "superadmin@pawguard.com",
        "test@example.com",
        "perf_owner_test@example.com"
    ]
    
    passwords = ["StrongP@ss99", "StrongPassword123!", "admin123", "password"]
    
    for email in test_emails:
        for p in passwords:
            st, res = test_login(email, p)
            if st == 200:
                user = res.get("data", {}).get("user", {})
                roles = user.get("roles", [])
                print(f"SUCCESS! Email: {email} | Password: {p} | Roles: {roles}")
                break

if __name__ == "__main__":
    main()
