"""Phase 0: rough text-quality score for extracted judgment text.

Noise = share of word tokens that look broken: contain OCR junk characters, mix letters and
digits oddly, or are 1-2 letter fragments that are not common short words. This is a crude
proxy to compare decades/courts, not an accuracy measurement.
"""
import re
import sys
from pathlib import Path

import pandas as pd

SHORT_OK = {"a", "i", "an", "as", "at", "be", "by", "do", "he", "if", "in", "is", "it", "me", "my",
            "no", "of", "on", "or", "so", "to", "up", "us", "we", "v", "s", "r", "j", "jj", "co",
            "vs", "mr", "dr", "ms", "nos", "no", "ii", "iv", "vi", "hc", "sc", "id", "ld"}
JUNK = re.compile(r"[~\\|{}^<>§¢£¥©®°±µ¶¤]|[a-z][A-Z]{2}|[a-zA-Z]\d[a-zA-Z]")


def noise(text):
    toks = re.findall(r"\S+", text)
    words = [t.strip(".,;:()[]\"'") for t in toks]
    words = [w for w in words if w]
    if not words:
        return None
    bad = sum(1 for w in words if JUNK.search(w) or (w.isalpha() and len(w) <= 2 and w.lower() not in SHORT_OK))
    return bad / len(words)


def main(folder):
    rows = []
    for f in Path(folder).glob("*_EN.txt"):
        rows.append({"file": f.name, "year": int(re.search(r"(\d{4})_", f.name).group(1)), "noise": noise(f.read_text(encoding="utf-8"))})
    df = pd.DataFrame(rows)
    print(df.groupby(df.year // 10 * 10).noise.agg(["count", "median", "max"]).round(3).to_string())
    print("worst:", df.sort_values("noise").tail(3).to_dict("records"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/raw/sc_sample")
