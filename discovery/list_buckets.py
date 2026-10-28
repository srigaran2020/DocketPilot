"""Phase 0: list the top levels of the open SC and HC judgment buckets (no AWS account needed)."""
import boto3
from botocore import UNSIGNED
from botocore.config import Config

BUCKETS = ["indian-supreme-court-judgments", "indian-high-court-judgments"]

s3 = boto3.client(
    "s3",
    region_name="ap-south-1",
    config=Config(signature_version=UNSIGNED, retries={"max_attempts": 10}, read_timeout=120),
)


def show(bucket, prefix="", depth=2, indent="  "):
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/", MaxKeys=60)
    for obj in resp.get("Contents", []):
        print(f"{indent}file {obj['Key']}  ({obj['Size']:,} bytes)")
    prefixes = [p["Prefix"] for p in resp.get("CommonPrefixes", [])]
    for p in prefixes[:25]:
        print(f"{indent}dir  {p}")
        if depth > 1:
            show(bucket, p, depth - 1, indent + "  ")
    if len(prefixes) > 25:
        print(f"{indent}... {len(prefixes) - 25} more dirs")
    if resp.get("IsTruncated"):
        print(f"{indent}... (truncated)")


for b in BUCKETS:
    print("==", b)
    show(b)
