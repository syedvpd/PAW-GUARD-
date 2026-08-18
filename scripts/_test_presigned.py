"""Generate presigned URLs that are long-lived enough for the app to use them."""
import boto3
from botocore.config import Config

s3 = boto3.client(
    "s3",
    endpoint_url="https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3",
    aws_access_key_id="c4c02c308590632cee3571c440ae82a7",
    aws_secret_access_key="905038743ca95bdc0d78e92d94693a7c2214e613242f8cc5a571f899614ebb18",
    region_name="ap-southeast-1",
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)

# Try longer expiry
for key in ["adoption images/ad1.jfif", "adoption images/ad2.webp", "adoption images/ad3.webp"]:
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": "pawguard-media", "Key": key},
        ExpiresIn=7 * 24 * 3600,  # 7 days
    )
    print(f"Key: {key}")
    print(f"URL: {url}")
    print()

# Also try to get the object directly (server-side, should work)
print("Trying direct get_object (server-side)...")
for key in ["adoption images/ad1.jfif", "adoption images/ad2.webp", "adoption images/ad3.webp"]:
    try:
        resp = s3.get_object(Bucket="pawguard-media", Key=key)
        body = resp["Body"].read()
        print(f"  {key}: {len(body)} bytes downloaded OK")
    except Exception as e:
        print(f"  {key}: ERROR {type(e).__name__}: {e}")
