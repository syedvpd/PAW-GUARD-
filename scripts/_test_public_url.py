"""Test different URL formats for Supabase S3 public access."""
import urllib.request
import urllib.parse

# Try the Supabase storage REST signed URL endpoint (different from S3)
# Supabase provides /storage/v1/object/sign/{bucket}/{path}?token=...
# But that needs a JWT. Let's just try the public path with proper encoding.

bucket = "pawguard-media"
path = "adoption images/ad1.jfif"
encoded_path = urllib.parse.quote(path, safe="/")

candidates = [
    f"https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/object/public/{bucket}/{encoded_path}",
    f"https://xzxsdgobndbkufyszzul.supabase.co/storage/v1/object/public/{bucket}/{encoded_path}",
    f"https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/object/sign/{bucket}/{encoded_path}",
]

for url in candidates:
    try:
        req = urllib.request.Request(url, method="HEAD")
        resp = urllib.request.urlopen(req, timeout=10)
        print(f"OK  status={resp.status}  {url}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}  {url}")
    except Exception as e:
        print(f"ERR {type(e).__name__}: {e}  {url}")
