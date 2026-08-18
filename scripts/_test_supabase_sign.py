"""Try Supabase REST API to get a signed URL via service role key."""
import os
import urllib.request
import urllib.error
import json

# Try the /storage/v1/object/sign/ endpoint with an Authorization header
# Supabase uses service_role JWT for full access

bucket = "pawguard-media"
path = "adoption images/ad1.jfif"

# Try with no auth (public bucket)
url = f"https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/object/sign/{bucket}/{path}"
req = urllib.request.Request(url, method="POST", headers={"Content-Type": "application/json"},
                             data=json.dumps({"expiresIn": 3600}).encode())
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"OK no-auth: {json.loads(resp.read())}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} no-auth body: {e.read().decode()[:200]}")

# Try as GET on object (signed URL token returned)
url2 = f"https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/object/sign/{bucket}/{path}?token=test"
try:
    resp = urllib.request.urlopen(url2, timeout=10)
    print(f"OK get: {resp.read()[:200]}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} get body: {e.read().decode()[:200]}")
