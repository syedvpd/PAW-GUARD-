import urllib.request, urllib.error
url = "https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3/pawguard-media/adoption%20images/ad1.jfif?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=c4c02c308590632cee3571c440ae82a7%2F20260817%2Fap-southeast-1%2Fs3%2Faws4_request&X-Amz-Date=20260817T112610Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=f4d437b3c0eace4e53565174d0f7bd0ac2563a6e9f3e7291e013323c896e3c55"
try:
    req = urllib.request.Request(url, method="HEAD")
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"OK status={resp.status} Content-Length={resp.headers.get('Content-Length')}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.reason}")
    try:
        print(e.read().decode()[:300])
    except Exception:
        pass
