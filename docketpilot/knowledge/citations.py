"""Find case citations in text and convert them to one canonical form (spec 8, Steps 1-2).

Supported: SC neutral (2023 INSC 123), HC neutral (2023:KER:1234), SCR ([2022] 7 S.C.R. 557),
SCC ((2019) 4 SCC 197), SCC OnLine (2019 SCC OnLine SC 123), AIR (AIR 1999 SC 1234),
Cr LJ (2005 Cri LJ 123). The original string is always kept for display.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Citation:
    kind: str  # neutral | hc_neutral | scr | scc | scc_online | air | crlj
    raw: str
    canonical: str
    year: int
    start: int
    end: int


_SEP = r"[\s.]*"
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("neutral", re.compile(r"\b((?:19|20)\d{2})\s*INSC\s*(\d{1,5})\b", re.I)),
    ("hc_neutral", re.compile(r"\b((?:19|20)\d{2}):([A-Z]{2,6}):(\d{1,6})(?:-([A-Z]{1,3}))?\b")),
    ("scr", re.compile(
        r"[\[(]((?:19|20)\d{2})[\])]\s*(SUPP(?:L)?\.?\s*)?(\d{1,2})\s*S\.?\s*C\.?\s*R\.?\s*(\d{1,5})\b", re.I)),
    ("scc_online", re.compile(
        r"\b((?:19|20)\d{2})\s*SCC\s*On\s*Line\s*([A-Z][A-Za-z]{1,6})\s*(\d{1,6})\b", re.I)),
    ("scc", re.compile(r"[\[(]((?:19|20)\d{2})[\])]\s*(\d{1,2})\s*S\.?\s*C\.?\s*C\.?\s*(\d{1,5})\b", re.I)),
    ("air", re.compile(r"\bA\.?\s*I\.?\s*R\.?\s*((?:19|20)\d{2})\s*([A-Z][A-Za-z.]{1,12}?)\s*(\d{1,5})\b")),
    ("crlj", re.compile(
        r"[\[(]?((?:19|20)\d{2})[\])]?\s*Cri?\.?\s*L\.?\s*J\.?\s*(\d{1,6})\b", re.I)),
]


def _canonical(kind: str, m: re.Match[str]) -> str:
    g = m.groups()
    if kind == "neutral":
        return f"{g[0]} INSC {int(g[1])}"
    if kind == "hc_neutral":
        suffix = f"-{g[3]}" if g[3] else ""
        return f"{g[0]}:{g[1].upper()}:{int(g[2])}{suffix}"
    if kind == "scr":
        supp = "SUPP " if g[1] else ""
        return f"{g[0]} {supp}{int(g[2])} SCR {int(g[3])}"
    if kind == "scc_online":
        return f"{g[0]} SCC ONLINE {g[1].upper()} {int(g[2])}"
    if kind == "scc":
        return f"{g[0]} {int(g[1])} SCC {int(g[2])}"
    if kind == "air":
        court = re.sub(r"[.\s]", "", g[1]).upper()
        return f"AIR {g[0]} {court} {int(g[2])}"
    if kind == "crlj":
        return f"{g[0]} CRLJ {int(g[1])}"
    raise ValueError(kind)


def find_citations(text: str) -> list[Citation]:
    """All citations in `text`, in order, without overlaps (earlier patterns win)."""
    found: list[Citation] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in PATTERNS:
        for m in pattern.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append(Citation(kind, m.group(0), _canonical(kind, m), int(m.group(1)), m.start(), m.end()))
    return sorted(found, key=lambda c: c.start)


def normalise(raw: str) -> Citation | None:
    """Canonical form of a single citation string, or None if it is not a recognised format."""
    hits = find_citations(raw)
    return hits[0] if hits else None


# Words around a citation that say how the citing court treated it (spec 5.4). Order = priority.
SIGNALS: list[tuple[str, re.Pattern[str]]] = [
    ("overruled", re.compile(r"\boverrul(?:ed|ing)\b", re.I)),
    ("per_incuriam", re.compile(r"\bper\s+incuriam\b", re.I)),
    ("doubted", re.compile(r"\bdoubt(?:ed|ing)\b|\bnot\s+good\s+law\b", re.I)),
    ("distinguished", re.compile(r"\bdistinguish(?:ed|able|ing)\b", re.I)),
    ("followed", re.compile(r"\bfollow(?:ed|ing)\b", re.I)),
    ("relied", re.compile(r"\brel(?:ied|ying|iance)\b", re.I)),
]


def signal_for(sentence: str) -> str:
    for name, pattern in SIGNALS:
        if pattern.search(sentence):
            return name
    return "cited"


def sentence_around(text: str, start: int, end: int, limit: int = 400) -> str:
    """The sentence containing [start, end), trimmed to about `limit` characters."""
    left = max(text.rfind(". ", 0, start), text.rfind("\n\n", 0, start))
    right_candidates = [i for i in (text.find(". ", end), text.find("\n\n", end)) if i != -1]
    right = min(right_candidates) if right_candidates else len(text)
    s = text[left + 1 if left != -1 else 0 : right + 1].strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > limit:
        mid = s.find(text[start:end].split()[0]) if text[start:end].split() else len(s) // 2
        lo = max(0, mid - limit // 2)
        s = s[lo : lo + limit]
    return s
