"""PII detection and redaction.

Rule-based recognisers for Indian identifiers + spaCy (en_core_web_sm) for names, organisations, places.
Recall matters more than precision here (spec 10.1), so rules err on the side of masking.
"""
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

# ---------- Aadhaar checksum (Verhoeff) ----------
_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
      [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
      [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
      [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
      [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
      [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_valid(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_digit(num: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


# ---------- rule recognisers ----------
RULES: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("AADHAAR", re.compile(r"\b[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]\b")),
    ("PHONE", re.compile(r"(?<![\w/])(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}\b")),
    ("IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    ("BANK_ACCOUNT", re.compile(r"(?i)(?:a/?c|account)\s*(?:no\.?|number|#)?\s*[:.-]?\s*(\d[\d\s-]{7,20}\d)")),
    ("VEHICLE", re.compile(r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{1,3}[\s-]?\d{4}\b")),
    ("ADDRESS", re.compile(  # "No. 21, Temple Street, Madurai - 625001"; never starts at a cheque/case number,
        # and never runs across words that belong to a transaction ("dated", "Rs.", "cheque", "for")
        r"(?i)(?<!cheque\s)(?<!cheque)(?<!memo\s)(?<!case\s)(?<!a/c\s)"
        r"\b(?:(?:door|house|flat|plot)\s*no\.?|no\.)\s*[\w/-]{1,8},?\s+"
        r"(?:(?!\b(?:dated|rs|cheque|for|amount|returned)\b)[^\n]){3,100}?(?:-|\s)\s*\d{6}\b")),
    ("PERSON", re.compile(  # honorifics and relation markers common in Indian legal documents
        r"\b(?:Mr|Mrs|Ms|Smt|Shri|Sri|Thiru|Tmt|Dr|Kumari|Selvi)\.?\s+((?:[A-Z]\.\s?)*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})"
        r"|\b(?:[SDW]/o|son of|daughter of|wife of)\s+((?:[A-Z]\.\s?)*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})"
        r"|\b(?:complainant|accused|drawer|payee|petitioner|respondent|proprietor|director|partner)\s+"
        r"((?:[A-Z]\.\s?)*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})")),
    ("ORG", re.compile(  # common Indian business-name endings
        r"\b((?:M/s\.?\s+)?(?:[A-Z][\w&'.-]*\s+){1,5}(?:Traders|Textiles|Agencies|Agency|Exports|Imports|Stores|"
        r"Enterprises|Industries|Company|Corporation|Associates|Finance|Finances|Motors|Builders|Hardware|"
        r"Constructions|Mills|Jewellers|Pharma|Foods)(?:\s+(?:Pvt\.?|Private))?(?:\s+(?:Ltd\.?|Limited|LLP))?"
        r"|(?:M/s\.?\s+)?(?:[A-Z][\w&'.-]*\s+){1,5}(?:Pvt\.?|Private)\s+(?:Ltd\.?|Limited)|"
        r"(?:[A-Z][\w&'.-]*\s+){1,4}&\s+Co\.?)")),
]
NER_LABELS = {"PERSON": "PERSON", "ORG": "ORG", "GPE": "PLACE", "LOC": "PLACE", "FAC": "PLACE"}
# Never mask the law itself or courts: the model needs them, and they are public.
KEEP = re.compile(r"(?i)\b(act|code|court|section|sanhita|adhiniyam|constitution|tribunal|magistrate|"
                  r"state of|union of india|reserve bank|supreme|high court|cheque|rupees|rs)\b")


@dataclass
class Entity:
    type: str
    start: int
    end: int
    value: str
    source: str  # rule | ner | user
    placeholder: str = ""


@dataclass
class Redaction:
    text: str
    entities: list[Entity]
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> real value


@lru_cache
def _nlp() -> Any:
    import spacy

    return spacy.load("en_core_web_sm", disable=["lemmatizer"])


def detect(text: str, use_ner: bool = True) -> list[Entity]:
    found: list[Entity] = []
    for typ, pat in RULES:
        for m in pat.finditer(text):
            if typ == "AADHAAR" and not verhoeff_valid(re.sub(r"\D", "", m.group(0))):
                continue
            g = next((i for i in range(1, (m.lastindex or 0) + 1) if m.group(i)), 0)
            found.append(Entity(typ, m.start(g), m.end(g), m.group(g), "rule"))
    if use_ner:
        for ent in _nlp()(text).ents:
            label = NER_LABELS.get(ent.label_)
            if label and len(ent.text.strip()) > 2 and not KEEP.search(ent.text):
                found.append(Entity(label, ent.start_char, ent.end_char, ent.text, "ner"))
    # Propagate: a value found once is masked everywhere it occurs (NER often spots a name only once).
    seen = {(e.type, e.value.strip()) for e in found if len(e.value.strip()) >= 4}
    for typ, value in seen:
        for m in re.finditer(rf"(?<!\w){re.escape(value)}(?!\w)", text):
            found.append(Entity(typ, m.start(), m.end(), value, "propagated"))
    # keep the longest non-overlapping spans; rules win ties
    found.sort(key=lambda e: (e.start, -(e.end - e.start), e.source != "rule"))
    out: list[Entity] = []
    for e in found:
        if out and e.start < out[-1].end:
            continue
        out.append(e)
    return out


def redact(text: str, mapping: dict[str, str] | None = None, extra: list[tuple[str, str]] | None = None,
           unmask: set[str] | None = None, use_ner: bool = True) -> Redaction:
    """mapping: existing placeholder->value map for this matter (keeps PERSON_1 the same across documents).
    extra: (type, value) pairs the lawyer added in the preview; unmask: values the lawyer said are not PII."""
    mapping = dict(mapping or {})
    reverse = {v.lower(): k for k, v in mapping.items()}
    entities = [e for e in detect(text, use_ner) if not (unmask and e.value in unmask)]
    for typ, value in extra or []:
        for m in re.finditer(re.escape(value), text):
            if not any(m.start() < e.end and e.start < m.end() for e in entities):
                entities.append(Entity(typ, m.start(), m.end(), value, "user"))
    entities.sort(key=lambda e: e.start)
    counters: dict[str, int] = {}
    for k in mapping:
        t, _, n = k.rpartition("_")
        if n.isdigit():
            counters[t] = max(counters.get(t, 0), int(n))
    parts, pos = [], 0
    for e in entities:
        key = e.value.strip().lower()
        ph = reverse.get(key)
        if ph is None:
            counters[e.type] = counters.get(e.type, 0) + 1
            ph = f"{e.type}_{counters[e.type]}"
            mapping[ph] = e.value.strip()
            reverse[key] = ph
        e.placeholder = ph
        parts.append(text[pos:e.start])
        parts.append(ph)
        pos = e.end
    parts.append(text[pos:])
    return Redaction("".join(parts), entities, mapping)


def restore(text: str, mapping: dict[str, str]) -> str:
    """Put real values back (only after the lawyer approves the draft). Longest placeholders first so
    PERSON_12 is not broken by PERSON_1."""
    for ph in sorted(mapping, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(ph)}\b", mapping[ph].replace("\\", "\\\\"), text)  # literal replacement
    return text
