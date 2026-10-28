"""Phase 0: sample criminal-matter PDFs per candidate HC bench; estimate Section 138 share and text quality.

Criminal matters are picked from the case-type prefix of the title. A judgment counts as a
Section 138 matter if its text mentions the Negotiable Instruments Act, or "138" next to a
section marker together with cheque/N.I. wording. Estimated 138 volume per bench =
criminal-matter count x sample share (a rough estimate with wide error bars at n=50).
"""
import re

import boto3
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config
from pypdf import PdfReader

from hc_courts import BENCHES, RAW, meta_key, pdf_key
from text_noise import noise

PER_BENCH = 50
MIN_CHARS = 200
BUCKET = "indian-high-court-judgments"
META = RAW / "hc_metadata"
OUT = RAW / "hc_sample"

CRIMINAL = re.compile(r"CRL|CRM|CRR|CRA|REVN|APEAL|^APL")
NI_ACT = re.compile(r"negotiable\s+instruments?|\bn\.\s?i\.?\s?act\b", re.I)
S138 = re.compile(r"(section|sec\.?|s\.|u/s\.?)\s*138\b", re.I)
CHEQUE = re.compile(r"cheque|dishonou?r", re.I)

s3 = boto3.client(
    "s3",
    region_name="ap-south-1",
    config=Config(signature_version=UNSIGNED, retries={"max_attempts": 10}, read_timeout=300),
)


def classify(text):
    ni = bool(NI_ACT.search(text))
    return ni or (bool(S138.search(text)) and bool(CHEQUE.search(text)))


rows = []
for label, court, bench in BENCHES:
    df = pd.read_parquet(META / meta_key(court, bench), columns=["title", "pdf_link", "cnr"])
    types = df.title.fillna("").str.extract(r"^\s*([^/]+?)\s*/")[0].str.upper().fillna("")
    crim = df[types.str.contains(CRIMINAL)]
    sample = crim.sample(min(PER_BENCH, len(crim)), random_state=11)
    out = OUT / bench
    out.mkdir(parents=True, exist_ok=True)
    for _, r in sample.iterrows():
        rec = {"bench": label, "n_judgments": len(df), "n_criminal": len(crim), "cnr": r.cnr,
               "title": r.title[:80]}
        dest = out / r.pdf_link.rsplit("/", 1)[-1]
        try:
            if not dest.exists():
                s3.download_file(BUCKET, pdf_key(court, bench, r.pdf_link), str(dest))
            pages = [p.extract_text() or "" for p in PdfReader(str(dest)).pages]
            text = "\n".join(pages)
            chars = [len(re.sub(r"\s", "", t)) for t in pages]
            rec.update(pages=len(pages), text_pages=sum(c >= MIN_CHARS for c in chars),
                       is_138=classify(text), noise=noise(text) if text.strip() else None)
            dest.with_suffix(".txt").write_text(text, encoding="utf-8")
        except Exception as e:  # missing PDF is itself a finding
            rec["error"] = f"{type(e).__name__}: {e}"[:120]
        rows.append(rec)
    print(f"done {label}", flush=True)

res = pd.DataFrame(rows)
res.to_csv(OUT / "_summary.csv", index=False)
ok = res[res["error"].isna()] if "error" in res else res
summary = ok.groupby("bench").agg(
    judgments=("n_judgments", "first"), criminal=("n_criminal", "first"), sampled=("cnr", "count"),
    s138_share=("is_138", "mean"), text_page_share=("text_pages", "sum"), pages=("pages", "sum"),
    noise_median=("noise", "median"),
)
summary["text_page_share"] = summary.text_page_share / summary.pages
summary["est_138_per_year"] = (summary.criminal * summary.s138_share).round(-1)
errors = res.groupby("bench")["error"].apply(lambda s: s.notna().sum()) if "error" in res else 0
summary["errors"] = errors
print(summary.drop(columns="pages").round(3).to_string())
