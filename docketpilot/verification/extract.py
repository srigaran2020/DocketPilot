"""Step 1: find citations (with the case name next to them), direct quotes and statute references in a draft."""
import re
from dataclasses import dataclass, field

from docketpilot.knowledge import citations as cit
from docketpilot.knowledge.statutes import ACT_ALIASES, act_short_name


@dataclass
class CitedItem:
    id: str
    raw: str  # what the draft says, e.g. "Rangappa v. Sri Mohan, (2010) 11 SCC 441"
    case_name: str | None
    citation: cit.Citation | None  # None for name-only citations like "Rangappa v. Sri Mohan (2010)"
    year: int | None
    start: int
    end: int
    proposition: str  # the sentence the citation supports, citation text removed
    quotes: list[str] = field(default_factory=list)


@dataclass
class StatuteRef:
    id: str
    raw: str
    section: str
    act: str
    start: int
    end: int
    quoted_text: str | None = None


# "A v. B", "A vs. B", "A versus B" -- names start with a capital letter
_NAME = r"[A-Z][\w.&'()/-]*(?:\s+(?:[A-Z][\w.&'()/-]*|of|and|the|&|@|alias|M/s\.?))*"
CASE_NAME = re.compile(rf"({_NAME})\s+(?:v\.?|vs\.?|versus)\s+({_NAME})")
NAME_YEAR = re.compile(rf"({_NAME})\s+(?:v\.?|vs\.?|versus)\s+({_NAME})\s*[,]?\s*[(\[]((?:19|20)\d{{2}})[)\]]")
QUOTE = re.compile(r"[\"“]([^\"”]{25,1500})[\"”]")
# Every Act in the statute store (by any common name) plus the repealed criminal codes, which the verifier flags.
_REPEALED = (r"IPC|I\.P\.C\.?|Indian\s+Penal\s+Code(?:,?\s*1860)?|Cr\.?\s?P\.?\s?C\.?|"
             r"Code\s+of\s+Criminal\s+Procedure(?:,?\s*1973)?|(?:Indian\s+)?Evidence\s+Act(?:,?\s*1872)?")
_ACT_ALT = "|".join(f"(?:{p})" for p, _ in ACT_ALIASES) + "|" + _REPEALED
STATUTE = re.compile(
    r"\b(?:Section|Sec\.?|S\.|u/s\.?|Sections)\s*(\d{1,4}[A-Z]{0,2})((?:\s*\([0-9a-z]{1,5}\))*)\s*"
    r"(?:of\s+the\s+|of\s+|,\s*(?:the\s+)?)?"
    rf"({_ACT_ALT})(?![\w])", re.I)


# A full stop ends a sentence only when it is not part of a legal abbreviation ("v.", "Ltd.", "No.", "S.C.R.",
# initials like "S. Hegde") and the next word starts with a capital letter or a quote.
_SENT_END = re.compile(
    r"(?<!\bv)(?<!\bvs)(?<!\bVs)(?<!\bLtd)(?<!\bNo)(?<!\bnos)(?<!\bCo)(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<!\bSmt)"
    r"(?<!\bSri)(?<!\bShri)(?<!\bOrs)(?<!\bAnr)(?<!\bRs)(?<!\bSec)(?<!\bArt)(?<!\bviz)(?<!\bi\.e)(?<!\be\.g)"
    r"(?<!\b[A-Za-z])\.\s+(?=[A-Z\"“])"
    r"|\n\s*\n"
    r"|\n(?=[ \t]*(?:[-•*]|\d{1,2}[.)])\s)")  # each bullet / numbered line is its own statement


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Sentence = text between real sentence ends or blank lines. A single line break is NOT a boundary:
    drafts and PDF text wrap sentences across lines."""
    left, right = 0, len(text)
    for m in _SENT_END.finditer(text):
        if m.end() <= start:
            left = m.end()
        elif m.start() >= end:
            right = m.start() + 1
            break
    return left, right


_LEAD_WORDS = re.compile(r"^(?:(?:In|See|Also|As|Per|Cf\.?|And|The\s+case\s+of|Read|Refer(?:\s+to)?|Check|Look(?:\s+up)?|"
                         r"Follow|Consider|Cite|Note|Under|Following|Applying)\s+)+")


def _clean_name(name: str) -> str:
    return _LEAD_WORDS.sub("", name.strip())


def _act_name(raw: str) -> str:
    return act_short_name(raw) or raw.strip()


def extract(text: str) -> tuple[list[CitedItem], list[StatuteRef]]:
    items: list[CitedItem] = []
    used: list[tuple[int, int]] = []
    for n, c in enumerate(cit.find_citations(text)):
        # case name: the "A v. B" closest before the citation, within 160 characters
        window_start = max(0, c.start - 160)
        names = list(CASE_NAME.finditer(text, window_start, c.start))
        name = None
        start = c.start
        if names:
            m = names[-1]
            gap = text[m.end():c.start]
            if len(gap) <= 25 and not cit.find_citations(gap):
                name = f"{_clean_name(m.group(1))} v. {m.group(2).strip()}"
                start = m.start() + (len(m.group(1)) - len(m.group(1).lstrip())) \
                    + (len(m.group(1).strip()) - len(_clean_name(m.group(1))))
        items.append(CitedItem(f"C{n + 1}", text[start:c.end], name, c, c.year, start, c.end, ""))
        used.append((start, c.end))
    # name + (year) without any reporter citation
    for m in NAME_YEAR.finditer(text):
        if any(m.start() < e and s < m.end() for s, e in used):
            continue
        items.append(CitedItem(f"C{len(items) + 1}", m.group(0), f"{_clean_name(m.group(1))} v. {m.group(2).strip()}",
                               None, int(m.group(3)), m.start(), m.end(), ""))
        used.append((m.start(), m.end()))
    items.sort(key=lambda i: i.start)
    for i, it in enumerate(items):
        it.id = f"C{i + 1}"
        s, e = _sentence_bounds(text, it.start, it.end)
        # Remove every citation in the sentence (not just this one): grouped citations "(A, cit; B, cit)"
        # would otherwise leave other case names inside the proposition the judge is asked about.
        parts, pos = [], s
        for other in items:
            if s <= other.start < e:
                parts.append(text[pos:other.start])
                pos = max(pos, other.end)
        parts.append(text[pos:e])
        prop = "".join(parts)
        prop = re.sub(r"\(\s*[;,\s]*\)", "", prop)  # brackets left empty by the removal
        prop = re.sub(r"\s+", " ", QUOTE.sub("", prop)).strip(" ,;:.\n")
        it.proposition = re.sub(r"\s+([,.;:])", r"\1", prop)
    # quotes belong to the nearest citation before them in the same paragraph (or just after, same sentence)
    for q in QUOTE.finditer(text):
        para_start = text.rfind("\n\n", 0, q.start())
        before = [it for it in items if para_start <= it.start < q.start()]
        after = [it for it in items if q.end() <= it.start and _sentence_bounds(text, q.start(), q.end())[1] >= it.start]
        owner = before[-1] if before else (after[0] if after else None)
        if owner:
            owner.quotes.append(q.group(1).strip())
    refs: list[StatuteRef] = []
    for n, m in enumerate(STATUTE.finditer(text)):
        ref = StatuteRef(f"S{n + 1}", m.group(0), m.group(1).upper(), _act_name(m.group(3)), m.start(), m.end())
        # a quote starting within a few words after the reference ("Section 139 says: "...")
        nxt = QUOTE.search(text, m.end())
        if nxt and len(text[m.end():nxt.start()].split()) <= 4:
            ref.quoted_text = nxt.group(1)
        refs.append(ref)
    return items, refs
