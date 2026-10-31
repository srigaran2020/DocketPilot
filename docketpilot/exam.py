"""AIBE practice questions built straight from the stored bare Acts. No LLM call, no Groq tokens.

Every question is made from one current section: its number, its heading, its Act, or a time period
quoted in its text. The right answer is copied from that section, so it is correct by construction
(as correct as the India Code text); the explanation shows the section text and its source link.
Wrong options come from neighbouring sections of the same Act, or other Acts of the same subject.
"""
import random
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import psycopg

# The 19 AIBE subjects (Bar Council of India syllabus) -> Acts in the statute store.
# Empty list = not in the knowledge base yet (case-law subjects, or text not loaded).
SUBJECTS: list[tuple[str, list[str], str]] = [
    ("Constitutional Law", [], "Constitution of India not loaded yet"),
    ("Criminal Law (BNS)", ["BNS"], ""),
    ("Criminal Procedure (BNSS)", ["BNSS"], ""),
    ("Evidence (BSA)", ["BSA"], ""),
    ("Civil Procedure and Limitation", ["CPC", "Limitation Act"], ""),
    ("Alternative Dispute Resolution", ["Arbitration Act", "Legal Services Act", "Commercial Courts Act"], ""),
    ("Family Law", ["Hindu Marriage Act", "Hindu Succession Act", "Special Marriage Act", "HAMA", "HMGA", "Guardians and Wards Act",
                    "DMMA", "Divorce Act", "Muslim Women Act 2019", "Family Courts Act", "DV Act", "PCMA", "Dowry Prohibition Act",
                    "Indian Succession Act"], "Uncodified Muslim personal law not covered"),
    ("Public Interest Litigation", [], "Case law only; not covered"),
    ("Administrative Law", ["RTI Act"], "Mostly case law; only the RTI Act is covered"),
    ("Professional Ethics", ["Advocates Act", "Contempt Act"], "BCI conduct rules not loaded yet"),
    ("Company Law", ["Companies Act", "LLP Act", "IBC", "Partnership Act"], ""),
    ("Environmental Law", ["Environment Act", "Water Act", "Air Act", "Forest Act", "Wild Life Act"], ""),
    ("Cyber Law", ["IT Act"], ""),
    ("Labour and Industrial Law", ["Code on Wages", "Industrial Relations Code", "Social Security Code", "OSH Code", "POSH Act"], ""),
    ("Torts, Motor Vehicles and Consumer Protection", ["Motor Vehicles Act", "Consumer Protection Act"], "Tort is case law; only the two Acts"),
    ("Taxation", ["CGST Act", "Customs Act"], "Income-tax Act, 1961 left out: replaced by the 2025 Act"),
    ("Contract, Specific Relief, Property and NI Act", ["Contract Act", "Specific Relief Act", "Transfer of Property Act", "Registration Act",
                                                      "Easements Act", "Trusts Act", "Sale of Goods Act", "Stamp Act", "NI Act"], ""),
    ("Land Acquisition", ["RFCTLARR Act"], ""),
    ("Intellectual Property", ["Copyright Act", "Trade Marks Act", "Patents Act"], "Designs Act not loaded yet"),
]
SUBJECT_OF = {act: name for name, acts, _ in SUBJECTS for act in acts}
KINDS = ("which_section", "which_heading", "which_act", "period")

_SKIP_HEADING = re.compile(r"omitted|repealed|^\W*\[|^\W*$|^(definitions?|interpretation)\b", re.I)
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "fourteen": 14, "fifteen": 15, "twenty": 20, "twenty-one": 21, "twenty-four": 24,
            "thirty": 30, "forty-five": 45, "sixty": 60, "ninety": 90, "one hundred and eighty": 180}
_NUMWORD = {v: k for k, v in _WORDNUM.items()}
_PERIOD = re.compile(r"\b(\d{1,3}|" + "|".join(sorted(map(re.escape, _WORDNUM), key=len, reverse=True)) + r")\s+(days|months|years)\b", re.I)
_TYPICAL = {"days": [7, 10, 14, 15, 21, 30, 45, 60, 90, 180], "months": [1, 2, 3, 4, 6, 9, 12, 18, 24],
            "years": [1, 2, 3, 5, 7, 10, 12, 14, 20]}


@dataclass(frozen=True)
class Sec:
    act: str  # short name
    act_title: str
    number: str
    heading: str
    order: int  # position in the Act


def _sort_key(number: str) -> tuple[int, str]:
    m = re.match(r"(\d+)(.*)", number)
    return (int(m.group(1)), m.group(2)) if m else (10**6, number)


def _the(title: str) -> str:
    """'The Customs Act, 1962' -> 'the Customs Act, 1962', for use mid-sentence."""
    return "the " + title[4:] if title.startswith("The ") else title


def _clean(heading: str) -> str:
    return heading.strip().rstrip(".").strip()


def _neighbours(target: Sec, pool: list[Sec], k: int, rng: random.Random, key: Any) -> list[Sec]:
    """k sections of the same Act near the target (harder than random ones), with distinct `key` values."""
    near = sorted((s for s in pool if s.act == target.act and s is not target), key=lambda s: abs(s.order - target.order))[:12]
    rng.shuffle(near)
    out, seen = [], {key(target)}
    for s in near:
        if key(s) not in seen:
            out.append(s)
            seen.add(key(s))
        if len(out) == k:
            break
    return out


def _options(correct: str, wrong: list[str], rng: random.Random) -> tuple[list[str], int]:
    opts = [correct, *wrong]
    rng.shuffle(opts)
    return opts, opts.index(correct)


def find_period(text: str) -> tuple[str, str, str] | None:
    """The first time period in a section ("fifteen days") as (sentence with the number blanked, number as written, unit)."""
    for sentence in re.split(r"(?<=[.;:])\s+|\n", text):
        m = _PERIOD.search(sentence)
        if m and 40 <= len(sentence) <= 320:
            blanked = sentence[:m.start(1)] + "_____" + sentence[m.end(1):]
            return blanked.strip(), m.group(1).lower(), m.group(2).lower()
    return None


def _period_distractors(number: str, unit: str, rng: random.Random) -> list[str]:
    """Three other typical periods, written the same way as the answer (words or digits)."""
    as_word = not number.isdigit()
    value = _WORDNUM.get(number.lower()) if as_word else int(number)
    pool = [v for v in _TYPICAL[unit] if v != value and (not as_word or v in _NUMWORD)]
    rng.shuffle(pool)
    return [_NUMWORD[v] if as_word else str(v) for v in pool[:3]]


def make_question(kind: str, target: Sec, pool: list[Sec], act_titles: dict[str, str], same_subject_acts: list[str],
                  text: str, source_url: str, rng: random.Random) -> dict[str, Any] | None:
    """One multiple-choice question about `target`, or None if this section cannot make that kind."""
    heading = _clean(target.heading)
    where = f"Section {target.number}, {target.act_title}"
    if kind == "which_section":
        wrong = _neighbours(target, pool, 3, rng, key=lambda s: s.number)
        if len(wrong) < 3:
            return None
        q = f"Which section of {_the(target.act_title)} deals with “{heading}”?"
        opts, ans = _options(f"Section {target.number}", [f"Section {s.number}" for s in wrong], rng)
    elif kind == "which_heading":
        wrong = _neighbours(target, pool, 3, rng, key=lambda s: _clean(s.heading).lower())
        if len(wrong) < 3:
            return None
        q = f"Section {target.number} of {_the(target.act_title)} deals with:"
        opts, ans = _options(heading, [_clean(s.heading) for s in wrong], rng)
    elif kind == "which_act":
        others = [a for a in same_subject_acts if a != target.act]
        if len(others) < 3:
            others += [a for a in act_titles if a != target.act and a not in others]
        rng.shuffle(others)
        q = f"“{heading}” is a provision of which Act?"
        opts, ans = _options(target.act_title, [act_titles[a] for a in others[:3]], rng)
    elif kind == "period":
        found = find_period(text)
        if not found:
            return None
        blanked, number, unit = found
        wrong_periods = _period_distractors(number, unit, rng)
        if len(wrong_periods) < 3:
            return None
        q = f"Fill in the blank ({where}, period in {unit}): “{blanked}”"
        opts, ans = _options(number, wrong_periods, rng)
    else:
        raise ValueError(kind)
    return {"kind": kind, "question": q, "options": opts, "answer": ans, "act": target.act, "section": target.number,
            "subject": SUBJECT_OF.get(target.act, ""), "heading": heading, "where": where,
            "excerpt": text[:700], "source_url": source_url, "status": "unverified"}


def _eligible(conn: psycopg.Connection, acts: list[str]) -> tuple[list[Sec], dict[str, str]]:
    """Current sections with a heading found in no other section of any Act (no repealed, omitted, definitions
    or boilerplate), so "which section" and "which Act" questions have exactly one right answer."""
    with conn.cursor() as cur:
        cur.execute("""SELECT a.short_name, a.title, sv.section_number, sv.heading FROM section_versions sv
                       JOIN acts a ON a.id = sv.act_id WHERE sv.valid_to IS NULL""")
        rows = cur.fetchall()
        cur.execute("SELECT short_name, title FROM acts")
        titles: dict[str, str] = dict(cur.fetchall())
    common = Counter(_clean(h).lower() for *_, h in rows)
    wanted = set(acts)
    by_act: dict[str, list[tuple[str, str, str]]] = {}
    for act, title, number, heading in rows:
        if act not in wanted:
            continue
        h = _clean(heading)
        if len(h) >= 8 and not _SKIP_HEADING.search(h) and common[h.lower()] == 1:
            by_act.setdefault(act, []).append((title, number, heading))
    out = []
    for act, secs in by_act.items():
        for i, (title, number, heading) in enumerate(sorted(secs, key=lambda r: _sort_key(r[1]))):
            out.append(Sec(act, title, number, heading, i))
    return out, titles


def subjects(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """The 19 AIBE subjects with how many usable sections the knowledge base holds for each."""
    pool, _ = _eligible(conn, [a for _, acts, _ in SUBJECTS for a in acts])
    count = Counter(SUBJECT_OF[s.act] for s in pool)
    return [{"name": name, "acts": acts, "sections": count.get(name, 0), "note": note,
             "coverage": "none" if not count.get(name) else ("partial" if note else "full")} for name, acts, note in SUBJECTS]


def build_quiz(conn: psycopg.Connection, subject: str | None, n: int, kinds: list[str] | None = None,
               seed: int | None = None) -> list[dict[str, Any]]:
    """n questions from one subject, or a mock test spread evenly over every covered subject (subject=None)."""
    rng = random.Random(seed)
    kinds = [k for k in (kinds or KINDS) if k in KINDS] or list(KINDS)
    names = [subject] if subject else [s for s, acts, _ in SUBJECTS if acts]
    acts = [a for s, al, _ in SUBJECTS if s in names for a in al]
    pool, titles = _eligible(conn, acts)
    by_subject: dict[str, list[Sec]] = {}
    for sec in pool:
        by_subject.setdefault(SUBJECT_OF[sec.act], []).append(sec)
    live = [name for name in names if by_subject.get(name)]
    if not live:
        return []
    quota = {name: n // len(live) + (1 if i < n % len(live) else 0) for i, name in enumerate(rng.sample(live, len(live)))}
    picks: list[tuple[str, Sec]] = []
    for name, k in quota.items():
        cands = by_subject[name][:]
        rng.shuffle(cands)
        picks += [(name, c) for c in cands[:k * 3]]  # spares for sections that cannot make the chosen kind
    texts = _texts(conn, [c for _, c in picks])
    out: list[dict[str, Any]] = []
    made = Counter[str]()
    for name, c in picks:
        if made[name] >= quota[name]:
            continue
        text, url = texts.get((c.act, c.number), ("", ""))
        subject_acts = next(al for sname, al, _ in SUBJECTS if sname == name)
        for kind in rng.sample(kinds, len(kinds)):
            q = make_question(kind, c, by_subject[name], titles, subject_acts, text, url, rng)
            if q:
                out.append(q)
                made[name] += 1
                break
    rng.shuffle(out)
    for i, q in enumerate(out):
        q["id"] = i + 1
    return out


def _texts(conn: psycopg.Connection, secs: list[Sec]) -> dict[tuple[str, str], tuple[str, str]]:
    if not secs:
        return {}
    with conn.cursor() as cur:
        cur.execute("""SELECT a.short_name, sv.section_number, left(sv.text, 4000), sv.source_url FROM section_versions sv
                       JOIN acts a ON a.id = sv.act_id
                       WHERE sv.valid_to IS NULL AND (a.short_name, sv.section_number) IN
                             (SELECT * FROM unnest(%s::text[], %s::text[]))""",
                    ([s.act for s in secs], [s.number for s in secs]))
        return {(r[0], r[1]): (r[2], r[3]) for r in cur.fetchall()}
