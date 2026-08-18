import urllib.request, urllib.error
from pawguard.services.storage_service import StorageService
s = StorageService()
# Try GET with a browser-like User-Agent (Flutter webview might send one)
url = s.generate_presigned_download_url(object_key="adoption images/ad1.jfif", expires_in=3600)
print(f"URL: {url[:200]}")
print()

# Test with GET (not HEAD) and browser headers
req = urllib.request.Request(url)
req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
req.add_header("Accept", "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5")
try:
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read()
    print(f"OK status={resp.status} bytes={len(data)} Content-Type={resp.headers.get('Content-Type')}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.reason}")
    try:
        body = e.read()
        print(f"Body: {body[:300]}")
    except Exception:
        pass
