import urllib.request, urllib.error
from pawguard.services.storage_service import StorageService
s = StorageService()
url = s.generate_presigned_download_url(object_key="adoption images/ad1.jfif", expires_in=3600)
print(f"URL: {url}")
try:
    req = urllib.request.Request(url, method="HEAD")
    resp = urllib.request.urlopen(req, timeout=10)
    cl = resp.headers.get("Content-Length")
    print(f"OK status={resp.status} Content-Length={cl}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.reason}")
    try:
        print(e.read().decode()[:300])
    except Exception:
        pass
