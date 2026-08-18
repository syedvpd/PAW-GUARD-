"""List adoption images in Supabase S3 bucket."""
import boto3
from botocore.config import Config

s3 = boto3.client(
    "s3",
    endpoint_url="https://xzxsdgobndbkufyszzul.storage.supabase.co/storage/v1/s3",
    aws_access_key_id="c4c02c308590632cee3571c440ae82a7",
    aws_secret_access_key="905038743ca95bdc0d78e92d94693a7c2214e613242f8cc5a571f899614ebb18",
    region_name="ap-southeast-1",
    config=Config(signature_version="s3v4"),
)

bucket = "pawguard-media"
prefix = "adoption images/"
print(f"Listing bucket={bucket} prefix={prefix!r}")
resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
for obj in resp.get("Contents", []):
    print(f"  {obj['Key']}  size={obj['Size']}")

print()
print("Top-level common prefixes (folders):")
resp2 = s3.list_objects_v2(Bucket=bucket, Delimiter="/")
for p in resp2.get("CommonPrefixes", [])[:20]:
    print(f"  folder: {p['Prefix']}")
