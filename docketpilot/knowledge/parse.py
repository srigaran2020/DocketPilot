"""Turn extracted PDF text into cleaned segments and search chunks (spec 5.3).

Prototype simplifications (docs/DECISIONS.md): roles are only 'headnote' (SCR editorial text, never
evidence) and 'body' (the court's own words). Finer rhetorical roles are future work.
"""
import re
from dataclasses import dataclass

PAGE_BREAK = "\f"

# SCR margin letters (A-H on their own line), bare page numbers, running headers.
_NOISE_LINE = re.compile(
    r"^\s*(?:[A-H]|[-.]?\s?[A-H]\s?\.?|\d{1,4}|.{0,40}SUPREME COURT REPORTS.{0,40}|\[\d{4}\].{0,25}S\.C\.R\.\s*\d*)\s*$",
    re.I,
)
_BODY_START = [
    re.compile(r"(?i)(?:the\s+)?judg(?:e)?ment\s+of\s+the\s+court\s+was\s+delivered\s+by[^\n]*\n"),
    re.compile(r"(?i)(?:the\s+following\s+)?judg(?:e)?ment\s+(?:was|of\s+the\s+court\s+was)\s+delivered[^\n]*\n"),
    re.compile(r"(?i)(?:CIVIL|CRIMINAL|ORIGINAL)\s+(?:APPELLATE\s+)?JURISDICTION"),
]


@dataclass(frozen=True)
class Seg:
    role: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ChunkSpan:
    role: str
    page: int
    start: int  # offsets into the cleaned full text
    end: int
    text: str


def clean(raw: str) -> str:
    """Drop margin letters, page numbers and running headers; keep \\f page breaks; join hyphenated breaks."""
    pages = []
    raw = raw.replace("\x00", "")  # some PDFs carry NUL bytes; PostgreSQL text cannot store them
    for page in raw.split(PAGE_BREAK):
        lines = [ln.rstrip() for ln in page.splitlines() if not _NOISE_LINE.match(ln)]
        text = "\n".join(lines)
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        pages.append(text.strip())
    return PAGE_BREAK.join(pages)


def split_headnote(text: str, is_scr: bool) -> list[Seg]:
    """SCR reports start with an editorial headnote. Everything before the judgment marker is 'headnote'."""
    if is_scr:
        for pattern in _BODY_START:
            m = pattern.search(text)
            if m and m.start() < len(text) * 0.7:
                cut = m.end() if pattern is not _BODY_START[-1] else m.start()
                return [Seg("headnote", 0, cut, text[:cut]), Seg("body", cut, len(text), text[cut:])]
    return [Seg("body", 0, len(text), text)]


def chunk(text: str, segments: list[Seg], size: int = 1200, overlap: int = 150) -> list[ChunkSpan]:
    """Paragraph-aware chunks of about `size` characters, never crossing a segment boundary."""
    out: list[ChunkSpan] = []
    for seg in segments:
        pos = seg.start
        while pos < seg.end:
            end = min(pos + size, seg.end)
            if end < seg.end:  # prefer to end at a paragraph, then a sentence
                window = text[pos:end]
                cut = max(window.rfind("\n\n"), window.rfind(". "))
                if cut > size // 2:
                    end = pos + cut + 1
            piece = text[pos:end].replace(PAGE_BREAK, "\n").strip()
            if len(piece) >= 40:
                out.append(ChunkSpan(seg.role, text.count(PAGE_BREAK, 0, pos) + 1, pos, end, piece))
            if end >= seg.end:
                break
            pos = max(end - overlap, pos + 1)
    return out


_NI_ACT = re.compile(r"negotiable\s+instruments?\s+act|\bN\.\s?I\.?\s?Act\b", re.I)
_S138 = re.compile(r"(?:section|sec\.?|s\.|u/s\.?)\s*138\b", re.I)
_CHEQUE = re.compile(r"\bcheque", re.I)


def is_s138(text: str) -> bool:
    """Section 138 NI Act matter: 138 cited as a section together with NI Act or cheque wording, repeatedly."""
    s138 = len(_S138.findall(text))
    return s138 >= 2 and (bool(_NI_ACT.search(text)) or len(_CHEQUE.findall(text)) >= 3)


_OUTCOMES: list[tuple[str, re.Pattern[str]]] = [
    ("compounded", re.compile(r"\bcompounded\b|\bcompounding\s+(?:is|stands)\s+(?:permitted|allowed)", re.I)),
    ("remanded", re.compile(r"\b(?:remanded|remitted)\s+(?:back\s+)?to\b", re.I)),
    ("acquitted", re.compile(r"\b(?:is|are|stands?)\s+acquitted\b|\bacquittal\s+is\s+(?:confirmed|upheld)", re.I)),
    ("convicted", re.compile(r"\bconviction\s+(?:is|stands)\s+(?:confirmed|upheld|maintained)", re.I)),
    ("allowed", re.compile(r"\b(?:is|are|stands?)\s+(?:partly\s+)?allowed\b", re.I)),
    ("dismissed", re.compile(r"\b(?:is|are|stands?)\s+dismissed\b", re.I)),
]
_DISPOSAL_MAP = {
    "dismissed": "dismissed", "appeal(s) allowed": "allowed", "case allowed": "allowed",
    "case partly allowed": "allowed", "leave granted & allowed": "allowed",
    "leave granted & dismissed": "dismissed", "remitted to lower court": "remanded", "rejected": "dismissed",
}


def outcome(text: str, disposal_nature: str | None = None) -> tuple[str, float]:
    """(outcome, confidence). Court metadata first; otherwise rules on the last part of the judgment.
    Anything unclear is 'unknown' (spec 5.3: never guess)."""
    if disposal_nature and disposal_nature.strip().lower() in _DISPOSAL_MAP:
        return _DISPOSAL_MAP[disposal_nature.strip().lower()], 0.95
    tail = text[-2500:]
    hits = [name for name, p in _OUTCOMES if p.search(tail)]
    if len(hits) == 1:
        return hits[0], 0.7
    if len(hits) > 1:
        return hits[0], 0.4 if hits[0] in ("compounded", "remanded") else 0.3
    return "unknown", 0.0
