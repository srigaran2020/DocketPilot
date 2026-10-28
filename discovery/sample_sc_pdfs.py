"""Phase 0: download a stratified sample of SC judgment PDFs and measure text-layer quality.

A page with fewer than MIN_CHARS extractable characters is counted as "no text layer"
(likely scanned), which is what decides whether OCR is needed.
"""
import json
import re
from pathlib import Path

import boto3
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config
from pypdf import PdfReader

PER_DECADE = 6
MIN_CHARS = 200
BUCKET = "indian-supreme-court-judgments"
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT = RAW / "sc_sample"

s3 = boto3.client(
    "s3",
    region_name="ap-south-1",
    config=Config(signature_version=UNSIGNED, retries={"max_attempts": 10}, read_timeout=120),
)

df = pd.read_pickle(RAW / "sc_metadata_all.pkl")
sample = df.groupby(df._year // 10 * 10, group_keys=False).apply(
    lambda g: g.sample(min(PER_DECADE, len(g)), random_state=7)
)

OUT.mkdir(parents=True, exist_ok=True)
results = []
for _, row in sample.iterrows():
    key = f"data/pdf/year={row._year}/english/{row.path}_EN.pdf"
    dest = OUT / f"{row.path}_EN.pdf"
    rec = {"year": int(row._year), "path": row.path, "citation": row.citation, "nc": row.nc_display}
    try:
        if not dest.exists():
            s3.download_file(BUCKET, key, str(dest))
        reader = PdfReader(str(dest))
        pages = [p.extract_text() or "" for p in reader.pages]
        chars = [len(re.sub(r"\s", "", t)) for t in pages]
        rec.update(
            pages=len(pages),
            text_pages=sum(c >= MIN_CHARS for c in chars),
            chars=sum(chars),
            has_nc_in_text=bool(re.search(r"\d{4}\s*INSC\s*\d+", " ".join(pages))),
        )
        (OUT / f"{row.path}_EN.txt").write_text("\n\f\n".join(pages), encoding="utf-8")
    except Exception as e:  # missing file or unreadable PDF is itself a finding
        rec["error"] = f"{type(e).__name__}: {e}"[:120]
    results.append(rec)
    print(rec, flush=True)

res = pd.DataFrame(results)
res.to_csv(OUT / "_summary.csv", index=False)
ok = res[res.error.isna()] if "error" in res else res
print("\n=== summary ===")
print(f"sampled {len(res)}, readable {len(ok)}, errors {len(res) - len(ok)}")
print(f"pages total {ok.pages.sum()}, pages with text layer {ok.text_pages.sum()} "
      f"({ok.text_pages.sum() / ok.pages.sum():.1%})")
print("docs fully text-layer:", (ok.text_pages == ok.pages).sum(), "/", len(ok))
print(ok.groupby(ok.year // 10 * 10).apply(lambda g: g.text_pages.sum() / g.pages.sum()).round(2).to_string())
print(json.dumps({"docs_with_neutral_citation_in_text": int(ok.has_nc_in_text.sum())}))
