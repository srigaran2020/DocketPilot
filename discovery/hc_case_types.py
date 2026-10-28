"""Phase 0: download one year of metadata for candidate HC benches and show case-type mix."""
import re
from pathlib import Path

import boto3
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config

from hc_courts import BENCHES, RAW, meta_key

BUCKET = "indian-high-court-judgments"
ROOT = RAW / "hc_metadata"
s3 = boto3.client(
    "s3",
    region_name="ap-south-1",
    config=Config(signature_version=UNSIGNED, retries={"max_attempts": 10}, read_timeout=300),
)

for label, court, bench in BENCHES:
    key = meta_key(court, bench)
    dest = ROOT / key
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(BUCKET, key, str(dest))
    df = pd.read_parquet(dest, columns=["title", "description", "pdf_link"])
    types = df.title.fillna("").str.extract(r"^\s*([^/]+?)\s*/")[0].str.upper().str.strip()
    print(f"\n== {label}: {len(df):,} judgments")
    print("   " + ", ".join(f"{t}={n}" for t, n in types.value_counts().head(14).items()))
    print("   sample title:", re.sub(r"\s+", " ", df.title.iloc[0])[:110])
