"""Case-file intelligence: find the case number (locally, before masking), extract parties and dated events
(LLM on masked text, every event must quote the papers), file the paper under the right case, and put the
dates on the calendar.

Names never reach the database in plain text: parties are stored as placeholders (PERSON_1) and shown with
real names only on screen, via the encrypted vault.
"""
import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from docketpilot.llm import LLMError, LLMUnavailable, get_llm, head_tail
from docketpilot.privacy import redact as pii
from docketpilot.privacy import vault
from docketpilot.verification.quotes import norm

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

# "H.M.O.P. No. 123 of 2025", "Crl.O.P.No.45/2024", "W.P.(C) No. 12 of 2023", "CRL OP(MD). No.8017 of 2023",
# "CRIMINAL PETITION NO: 2968 OF 2023", "WRIT PETITION NO: 2730 0F 2021" (OCR'd zero for O)
_OF = r"(?:of|OF|Of|0F|/)"
_CASE_NO = re.compile(
    r"\b((?:[A-Z][A-Za-z]{0,10}\.?\s?){1,5}(?:\([A-Z]{1,4}\)\.?\s?)?)(?:No|NO)[.:]?\s*:?\s*(\d{1,6})\s*" + _OF + r"\s*((?:19|20)\d{2})\b")
# eCourts style "CRL OP/14527/2023", "HMOP/123/2025"
_CASE_SLASH = re.compile(r"\b([A-Z][A-Z.() ]{1,14}[A-Z.)])\s*/\s*(\d{1,6})\s*/\s*((?:19|20)\d{2})\b")
# Short form typed by lawyers: "HMOP 214/2026", "H.M.O.P. 214 of 2026", "CRL.OP 45/2024" (type in capitals only)
_CASE_SHORT = re.compile(r"(?<![\w.])([A-Z](?:[A-Z.]{1,11})(?:\s?\([A-Z]{1,4}\))?)\s+(\d{1,6})\s*(?:of|/)\s*((?:19|20)\d{2})\b")
_NOT_CASE = re.compile(r"^(?:CHEQUE|CHQ|A/?C|ACCOUNT|PHONE|MOBILE|DOOR|HOUSE|FLAT|PLOT|RS|SURVEY|FIR|AADHAAR|PAN|VEHICLE|"
                       r"ACT|SECTION|SEC|RULE|RULES|ORDER|ARTICLE|ART|CHAPTER|PARA|PAGE|ITEM|SCHEDULE|INSC|SCR|SCC|AIR|CRLJ)$")


@dataclass(frozen=True)
class CaseNumber:
    display: str  # "H.M.O.P. No. 123 of 2025"
    key: str      # "HMOP-123-2025" (for matching the same case across papers)


# Numbers that are not the case's own number: crime/FIR numbers, and the police or lower-court case it came from.
_NOT_OWN = re.compile(r"^(?:CRIME|CR|CRNO|FIRNO|RC|ORDER|JUDGMENT|COMMON|IN|AND|WITH|BEFORE|THE|JR|DATED)$")
# Trial-court numbers: the case itself in a trial-court paper, but in an appeal they name the case below.
_LOWER = re.compile(r"^(?:CC|STC|PRC|SC|MC|OS|OA|EP|EA|IA)$")
# Applications filed inside a case (interim applications, miscellaneous petitions): real numbers, but not the case.
_INSIDE = re.compile(r"^(?:IA|IAN|IANO|MP|CMP|WMP|CRLMP|CRLMPMD|CMPMD|WMPMD|SUBAPPL|VAKALAT|CAVEAT)$")
# Spelled-out case types -> the short form used on the cause list, so both spellings match the same case file.
_SPELLED = {"CRIMINALPETITION": "CRLP", "WRITPETITION": "WP", "WRITAPPEAL": "WA", "CRIMINALREVISIONCASE": "CRLRC",
            "CRIMINALREVISIONPETITION": "CRLRP", "CRIMINALAPPEAL": "CRLA", "BAILAPPL": "BA", "BAILAPPLICATION": "BA",
            "CIVILREVISIONPETITION": "CRP", "SECONDAPPEAL": "SA", "FIRSTAPPEAL": "FA", "CIVILMISCAPPEAL": "CMA",
            "MISCELLANEOUSFIRSTAPPEAL": "MFA", "ORIGINALPETITION": "OP", "APPEALSUIT": "AS", "CONTEMPTPETITION": "CONTP"}
_LEAD_JUNK = re.compile(r"^(?:(?:ORDER|JUDGMENT|COMMON|IN|AND|WITH|BEFORE|THE|Jr|DATED|ON)\s+)+")


_TYPE_WORDS = {"WRIT", "PETITION", "PETN", "CRIMINAL", "CIVIL", "REVISION", "CASE", "APPEAL", "BAIL", "APPL", "APPLN",
               "APPLICATION", "SECOND", "FIRST", "MISC", "MISCELLANEOUS", "ORIGINAL", "CONTEMPT", "SUIT", "TRANSFER",
               "REVIEW", "EXECUTION", "MATRIMONIAL", "MAT", "ARBITRATION", "COMMERCIAL", "CONSUMER", "COMPLAINT",
               "REGULAR", "SPECIAL", "SESSIONS", "LETTERS", "PATENT"}


def _type_part(raw: str) -> str:
    """Keep only the trailing words that look like a case type: 'COIMBATORE. H.M.O.P.' -> 'H.M.O.P.',
    'JUSTICE K. SARATH WRIT PETITION' -> 'WRIT PETITION'."""
    def is_type(tok: str) -> bool:
        core = tok.strip(".,:")
        return (core.upper() in _TYPE_WORDS or bool(re.fullmatch(r"(?:[A-Za-z]{1,4}\.)+[A-Za-z]{0,4}\.?(?:\([A-Z]{1,4}\)\.?)?", tok))
                or bool(re.fullmatch(r"[A-Z]{1,5}(?:\([A-Z]{1,4}\))?\.?", tok)) or bool(re.fullmatch(r"\([A-Z]{1,4}\)\.?", tok)))
    toks = raw.split()
    keep: list[str] = []
    for tok in reversed(toks):
        if not is_type(tok):
            break
        keep.insert(0, tok)
    # a lone initial ("K.") left over from a judge's name is not a type
    while len(keep) > 1 and re.fullmatch(r"[A-Z]\.", keep[0]) and keep[1].strip(".").upper() in _TYPE_WORDS:
        keep.pop(0)
    return " ".join(keep)


def find_case_number(text: str) -> CaseNumber | None:
    """Deterministic, local: runs on the raw text before anything is sent anywhere. Every candidate is scored:
    the cause title near the top wins; crime/FIR and lower-court numbers are skipped; applications filed inside a
    case (I.A., Crl.M.P.) rank below the case itself."""
    best: tuple[float, CaseNumber] | None = None
    for rank, pattern in enumerate((_CASE_NO, _CASE_SLASH, _CASE_SHORT)):
        for m in pattern.finditer(text):
            raw_kind = _type_part(_LEAD_JUNK.sub("", re.sub(r"\s+", " ", m.group(1)).strip()))
            kind = re.sub(r"[^A-Za-z]", "", raw_kind).upper()
            kind = _SPELLED.get(kind, kind)
            if not kind or len(kind) > 26 or _NOT_CASE.match(kind) or _NOT_OWN.match(kind) or kind in {"NO", "OF"}:
                continue
            score = -m.start() / 2000 - rank * 0.5 - (3 if _INSIDE.match(kind) else 0) - (1.5 if _LOWER.match(kind) else 0)
            whole = re.sub(r"\s+", " ", m.group(0)).strip()
            display = whole[whole.rfind(raw_kind):] if raw_kind and raw_kind in whole else _LEAD_JUNK.sub("", whole)
            cand = CaseNumber(display, f"{kind}-{int(m.group(2))}-{m.group(3)}")
            if best is None or score > best[0]:
                best = (score, cand)
    return best[1] if best else None


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_number": {"type": ["string", "null"]},
        "court": {"type": ["string", "null"]},
        "case_type": {"type": ["string", "null"]},
        "petitioner": {"type": ["string", "null"]},
        "respondent": {"type": ["string", "null"]},
        "events": {"type": "array", "items": {
            "type": "object",
            "properties": {"date": {"type": "string"}, "title": {"type": "string"},
                           "kind": {"type": "string", "enum": ["hearing", "filing", "notice", "order", "deadline", "other"]},
                           "quote": {"type": "string"}},
            "required": ["date", "title", "kind", "quote"], "additionalProperties": False}},
    },
    "required": ["case_number", "court", "case_type", "petitioner", "respondent", "events"],
    "additionalProperties": False,
}


_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_DATE = re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?(?:\s+day\s+of)?[\s./-]*(?:\d{{1,2}}|{_MONTH})[\s.,/-]*(?:19|20)?\d{{2}}\b"
                   rf"|\b{_MONTH}\s+\d{{1,2}},?\s+(?:19|20)\d{{2}}\b", re.I)


def condense(text: str, head: int = 2500, window: int = 220, limit: int = 9000) -> str:
    """What the date reader needs: the cause title (case number, court, parties) and the sentences around each
    date. A 30-page judgment becomes a few thousand characters: faster, cheaper, and less of the paper leaves the
    machine. Every line is copied verbatim, so quotes can still be checked against the full paper."""
    spans: list[tuple[int, int]] = []
    for m in _DATE.finditer(text, head):
        s, e = max(head, m.start() - window), min(len(text), m.end() + window // 2)
        if spans and s <= spans[-1][1]:
            spans[-1] = (spans[-1][0], e)
        else:
            spans.append((s, e))
    parts, size = [text[:head]], head
    for s, e in spans:
        if size + (e - s) > limit:
            break
        parts.append(text[s:e])
        size += e - s
    out = "\n[...]\n".join(parts)
    return out if len(out) < 0.8 * len(text) else head_tail(text)


async def extract_info(masked_text: str) -> dict[str, Any]:
    """Parties and dated events from masked text. Events whose quote is not in the papers are dropped."""
    messages = [{"role": "system", "content": (PROMPTS / "casefile_v1.md").read_text(encoding="utf-8")},
                {"role": "user", "content": condense(masked_text)}]
    llm = get_llm()
    last: Exception | None = None
    for effort, tokens in (("low", 4000), ("low", 8000)):
        try:
            r = await llm.complete(messages, reasoning_effort=effort, max_tokens=tokens, json_schema=SCHEMA,  # type: ignore[arg-type]
                                   schema_name="case_info")
            info = json.loads(r.text)
            break
        except (LLMError, json.JSONDecodeError) as e:
            last = e
    else:
        raise LLMError(f"case details could not be read: {last}")
    text_n = norm(masked_text).replace(" ", "")
    good = []
    for ev in info.get("events", []):
        try:
            d = date.fromisoformat(ev["date"][:10])
        except ValueError:
            continue
        q = norm(ev.get("quote", "")).replace(" ", "")
        if q and q in text_n:  # the date must be visibly in the papers
            good.append({**ev, "date": d.isoformat()})
    info["events"] = good
    return info


def _matter_by_key(conn: Any, firm_id: Any, key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id::text, title FROM matters WHERE firm_id=%s AND facts->>'case_key'=%s "
                    "ORDER BY created_at LIMIT 1", (firm_id, key))
        r = cur.fetchone()
    return {"id": r[0], "title": r[1]} if r else None


def choose_matter(conn: Any, firm_id: Any, raw_text: str, selected: str | None) -> dict[str, Any]:
    """Where does this paper belong? Same case number -> that case file. Otherwise the case file the lawyer
    has open, unless that file already belongs to a *different* case number. Otherwise a new case file."""
    cn = find_case_number(raw_text)
    if cn:
        hit = _matter_by_key(conn, firm_id, cn.key)
        if hit:
            return {**hit, "case_number": cn.display, "case_key": cn.key, "new": False}
    if selected:
        with conn.cursor() as cur:
            cur.execute("SELECT id::text, title, facts->>'case_key' FROM matters WHERE id=%s AND firm_id=%s", (selected, firm_id))
            r = cur.fetchone()
        if r and (not cn or not r[2] or r[2] == cn.key):
            return {"id": r[0], "title": r[1], "case_number": cn.display if cn else None,
                    "case_key": cn.key if cn else None, "new": False}
    return {"id": None, "title": cn.display if cn else None, "case_number": cn.display if cn else None,
            "case_key": cn.key if cn else None, "new": True}


def create_matter(conn: Any, firm_id: Any, user_id: Any, title: str | None, case_number: str | None,
                  case_key: str | None) -> str:
    mid = uuid.uuid4()
    conn.execute("INSERT INTO matters (id, firm_id, title, case_number, facts, created_by) VALUES (%s,%s,%s,%s,%s,%s)",
                 (mid, firm_id, title or f"New case · {date.today():%d %b %Y}", case_number,
                  json.dumps({"case_key": case_key} if case_key else {}), user_id))
    conn.commit()
    return str(mid)


def _event_id(ev: dict[str, Any]) -> str:
    h = hashlib.sha1(f"{ev['date']}|{ev['title'].lower()}".encode(), usedforsecurity=False).hexdigest()[:10]
    return f"doc-{ev['kind']}-{h}"


def apply_info(conn: Any, matter_id: str, info: dict[str, Any], filename: str) -> list[dict[str, Any]]:
    """Update the case file's details and put every extracted date on the calendar."""
    with conn.cursor() as cur:
        cur.execute("SELECT facts, case_number, court FROM matters WHERE id=%s", (matter_id,))
        facts, case_number, court = cur.fetchone()
    facts = dict(facts or {})
    for k in ("petitioner", "respondent", "case_type"):
        if info.get(k) and not facts.get(k):
            facts[k] = info[k]
    if info.get("case_number") and not case_number:
        cn = find_case_number(info["case_number"])
        case_number = info["case_number"]
        if cn and not facts.get("case_key"):
            facts["case_key"] = cn.key
    conn.execute("UPDATE matters SET facts=%s, case_number=%s, court=coalesce(court, %s) WHERE id=%s",
                 (json.dumps(facts), case_number, info.get("court"), matter_id))
    created = []
    for ev in info.get("events", []):
        due = date.fromisoformat(ev["date"])
        warn = due - timedelta(days=2 if ev["kind"] == "hearing" else 1)
        rid = _event_id(ev)
        cur = conn.execute("""INSERT INTO reminders (id, matter_id, rule_id, title, due_date, warn_on, source)
                              VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (matter_id, rule_id) DO NOTHING""",
                           (uuid.uuid4(), matter_id, rid, ev["title"][:200], due, warn,
                            f"From {filename}: “{ev['quote'][:200]}”"))
        if cur.rowcount:
            created.append({"date": ev["date"], "title": ev["title"], "kind": ev["kind"]})
    conn.commit()
    return created


def analyze(conn: Any, matter_id: str, masked_text: str, filename: str) -> dict[str, Any]:
    """Run extraction and filing for one confirmed paper. AI problems never block the upload itself."""
    try:
        info = asyncio.run(extract_info(masked_text))
    except (LLMUnavailable, LLMError) as e:
        return {"events": [], "error": f"Dates could not be read right now ({e}). The paper is saved; "
                                         "re-run later from the case file."}
    return {"events": apply_info(conn, matter_id, info, filename), "info": info}


def names(matter_id: str) -> dict[str, str]:
    """placeholder -> real value, for showing names on screen only."""
    try:
        return vault.load(matter_id)
    except vault.VaultError:
        return {}


def show(text: str | None, mapping: dict[str, str]) -> str | None:
    return pii.restore(text, mapping) if text else text
