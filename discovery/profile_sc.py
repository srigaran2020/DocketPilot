"""Phase 0: profile Supreme Court metadata (field completeness, coverage, Section 138 share)."""
from pathlib import Path

import pandas as pd

df = pd.read_pickle(Path(__file__).resolve().parent.parent / "data" / "raw" / "sc_metadata_all.pkl")


def filled(col):
    s = df[col].astype("string").fillna("").str.strip()
    return (s != "").mean() * 100


print(f"rows: {len(df):,}   years: {df._year.min()}-{df._year.max()}")
print("\nfield completeness (% non-empty):")
for c in ["title", "petitioner", "respondent", "description", "judge", "author_judge", "citation",
          "case_id", "cnr", "decision_date", "disposal_nature", "nc_display", "path", "available_languages"]:
    print(f"  {c:20s} {filled(c):5.1f}")

print("\nrows by decade:")
print(df.groupby(df._year // 10 * 10).size().to_string())

print("\ncitation format samples:")
print(df.citation.dropna().sample(8, random_state=1).to_string())
print("\nnc_display samples (non-empty):")
nc = df.nc_display.fillna("")
print(nc[nc != ""].sample(5, random_state=1).to_string())
print("\ndisposal_nature top 15:")
print(df.disposal_nature.value_counts().head(15).to_string())

text = (df.title.fillna("") + " " + df.description.fillna("")).str.lower()
ni = text.str.contains(r"negotiable instruments?|n\.\s?i\.\s?act")
s138 = text.str.contains(r"\b138\b") & (ni | text.str.contains("cheque|dishonour"))
cheque = text.str.contains(r"cheque")
print(f"\nmentions NI Act in title/description: {ni.sum():,}")
print(f"mentions 138 + NI/cheque: {s138.sum():,}")
print(f"mentions cheque: {cheque.sum():,}")
print("\nSection 138 hits by year (description-based, lower bound):")
print(df[s138].groupby("_year").size().to_string())
print("\ndescription filled by year (share):")
d = df.description.fillna("").str.strip() != ""
print(d.groupby(df._year // 5 * 5).mean().round(2).to_string())
