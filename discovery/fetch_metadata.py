"""Phase 0: download Parquet metadata files from the open judgment buckets.

Usage:
  python discovery/fetch_metadata.py sc                  # all SC years
  python discovery/fetch_metadata.py hc 2015 2025        # HC years 2015..2025, all courts

Files land in data/raw/<sc|hc>_metadata/ mirroring the bucket path. Already-downloaded
files are skipped, so the script can be re-run after a network failure.
"""
import sys
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

BUCKETS = {"sc": "indian-supreme-court-judgments", "hc": "indian-high-court-judgments"}
ROOT = Path(__file__).resolve().parent.parent / "data" / "raw"

s3 = boto3.client(
    "s3",
    region_name="ap-south-1",
    config=Config(signature_version=UNSIGNED, retries={"max_attempts": 10}, read_timeout=120),
)


def keys(bucket, prefix):
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                yield obj["Key"], obj["Size"]


def main():
    which = sys.argv[1]
    bucket = BUCKETS[which]
    if which == "sc":
        prefixes = ["metadata/parquet/"]
    else:
        lo, hi = int(sys.argv[2]), int(sys.argv[3])
        prefixes = [f"metadata/parquet/year={y}/" for y in range(lo, hi + 1)]

    out_root = ROOT / f"{which}_metadata"
    total = fetched = 0
    for prefix in prefixes:
        for key, size in keys(bucket, prefix):
            dest = out_root / key
            total += size
            if dest.exists() and dest.stat().st_size == size:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(dest))
            fetched += 1
            print(f"got {key} ({size:,} bytes)", flush=True)
    print(f"done: {fetched} new files, {total / 1e6:.1f} MB total under {out_root}")


if __name__ == "__main__":
    main()
