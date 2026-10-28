"""Phase 0: spot-check the Section 138 matches from sample_hc_pdfs.py and list scanned (no-text) PDFs."""
import re

import pandas as pd

from hc_courts import RAW

SAMPLE = RAW / "hc_sample"
r = pd.read_csv(SAMPLE / "_summary.csv")
pos = r[r.is_138 == True]  # noqa: E712 (column may hold NaN for failed rows)
print(len(pos), "matches")
for _, x in pos.iterrows():
    files = list(SAMPLE.glob(f"*/{x.cnr}*.txt"))
    t = files[0].read_text(encoding="utf-8") if files else ""
    s138 = len(re.findall(r"\b138\b", t))
    ni = len(re.findall(r"negotiable", t, re.I))
    print(f"{x.bench[:14]:14} 138x{s138:<3} NIx{ni:<3} {x.title[:70]}")

print("\nPDFs with no text layer at all:", int((r.text_pages == 0).sum()), "of", len(r))
print(r[r.text_pages == 0].groupby("bench").size().to_string())
