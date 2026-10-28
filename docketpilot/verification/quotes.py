"""Step 5: find a direct quote in a judgment's text, after normalising whitespace, case, quotes and punctuation."""
import difflib
import re
import unicodedata
from dataclasses import dataclass

NEAR_EXACT = 0.90


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class QuoteMatch:
    status: str  # exact | near_exact | not_found
    similarity: float
    found_text: str | None  # the matching passage from the judgment (normalised form)
    diff: list[str]


def _squash(s: str) -> str:
    return s.replace(" ", "")


def find_quote(quote: str, judgment_text: str) -> QuoteMatch:
    q, t = norm(quote), norm(judgment_text)
    if not q:
        return QuoteMatch("not_found", 0.0, None, [])
    if q in t:
        return QuoteMatch("exact", 1.0, q, [])
    # PDF text often splits words ("cheq ue"); ignoring spaces still means the same characters in order.
    if _squash(q) in _squash(t):
        return QuoteMatch("exact", 1.0, q, ["(matched ignoring spacing errors in the source PDF)"])
    words = q.split()
    # Anchor on the rarest-looking (longest) words, compare same-length windows around each occurrence.
    anchors = sorted(set(words), key=len, reverse=True)[:4]
    best = (0.0, "")
    for a in anchors:
        offset = q.find(a)
        for m in re.finditer(re.escape(a), t):
            start = max(0, m.start() - offset - 20)
            window = t[start:start + len(q) + 40]
            sm = difflib.SequenceMatcher(None, q, window, autojunk=False)
            blk = max(sm.get_matching_blocks(), key=lambda b: b.size)
            # tighten the window to the best-aligned span
            lo = max(0, blk.b - blk.a)
            cand = window[lo:lo + len(q)]
            ratio = difflib.SequenceMatcher(None, _squash(q), _squash(cand), autojunk=False).ratio()
            if ratio > best[0]:
                best = (ratio, cand)
    ratio, cand = best
    if ratio >= NEAR_EXACT:
        diff = [d for d in difflib.ndiff(cand.split(), q.split()) if d[:1] in "+-"]
        return QuoteMatch("near_exact", round(ratio, 3), cand, diff)
    return QuoteMatch("not_found", round(ratio, 3), None, [])
