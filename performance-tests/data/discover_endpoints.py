import urllib.request
import json
import ssl

BASE_URL = "https://pawguard-backend-mqri.onrender.com"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def main():
    url = f"{BASE_URL}/openapi.json"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, context=ctx) as resp:
        schema = json.loads(resp.read().decode("utf-8"))
    
    paths = schema.get("paths", {})
    print(f"Total OpenAPI paths: {len(paths)}")
    
    companion_pets = []
    medical = []
    admin = []
    auth = []
    
    for p, methods in paths.items():
        for m in methods.keys():
            if m in ("get", "post", "put", "patch", "delete"):
                endpoint_str = f"{m.upper()} /api/v1{p}" if not p.startswith("/api/v1") else f"{m.upper()} {p}"
                if "/companion-pets" in p:
                    companion_pets.append(endpoint_str)
                elif "/medical" in p:
                    medical.append(endpoint_str)
                elif "/admin" in p or "/dashboards" in p or "/reports" in p:
                    admin.append(endpoint_str)
                elif "/auth" in p:
                    auth.append(endpoint_str)
                    
    print("\n--- Companion Pets APIs ---")
    for ep in companion_pets:
        print(ep)
        
    print("\n--- Medical / Vet APIs ---")
    for ep in medical:
        print(ep)
        
    print("\n--- Admin APIs ---")
    for ep in admin:
        print(ep)

if __name__ == "__main__":
    main()
