"""Test if presigned URLs are accessible via browser-like GET request."""

import urllib.request, urllib.error
from pawguard.services.storage_service import StorageService

s = StorageService()
url = s.generate_presigned_download_url(object_key="adoption images/ad1.jfif", expires_in=3600)
print(f"URL: {url[:150]}...")

# Test with full browser-like request
req = urllib.request.Request(url)
req.add_header("User-Agent", "Mozilla/5.0")
req.add_header("Accept", "image/avif,image/webp,image/png,image/*;q=0.8")
req.add_header("Origin", "https://pawguard-web-gamma.vercel.app")
try:
    resp = urllib.request.urlopen(req, timeout=10)
    ct = resp.headers.get("Content-Type")
    cl = resp.headers.get("Content-Length")
    acao = resp.headers.get("Access-Control-Allow-Origin")
    print(f"OK status={resp.status}  Content-Type={ct}  Length={cl}  CORS={acao}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.reason}")
    for h in e.headers.items():
        print(f"  {h[0]}: {h[1][:100]}")
