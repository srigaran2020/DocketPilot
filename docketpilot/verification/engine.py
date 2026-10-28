"""Citation verification (spec Section 8, Steps 2-9).

Only Step 6 uses an LLM, and its answer is rejected unless it quotes text that really is in the passages.
Verdicts never say "fake": NOT_FOUND means "not found in our corpus".
"""
import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

from docketpilot.llm import LLMError, LLMProvider, LLMUnavailable
from docketpilot.retrieval import search
from docketpilot.verification.extract import CitedItem, StatuteRef, extract
from docketpilot.verification.quotes import find_quote, norm

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
RULES = Path(__file__).resolve().parents[2] / "data" / "rules"
NAME_MATCH = 0.45   # trigram similarity: case name in draft vs title in corpus
NAME_CONFLICT = 0.2  # below this, a resolved citation points to a different case


@dataclass
class Candidate:
    case_id: str
    title: str
    court: str
    year: int | None
    decision_date: str | None
    has_text: bool
    name_similarity: float | None
    via: str  # exact | alias | name_year


@dataclass
class CitationResult:
    id: str
    raw: str
    case_name: str | None
    canonical: str | None
    verdict: str  # VERIFIED | PARTIAL | NOT_FOUND | CONFLICT
    reason: str
    candidates: list[Candidate] = field(default_factory=list)
    quotes: list[dict[str, Any]] = field(default_factory=list)
    proposition: dict[str, Any] | None = None
    good_law: list[dict[str, Any]] = field(default_factory=list)
    colour: str = "red"
    start: int = 0  # where the citation sits in the checked text (used by auto-correction)
    end: int = 0
    year: int | None = None


@dataclass
class StatuteResult:
    id: str
    raw: str
    act: str
    section: str
    status: str  # in_force | not_yet_in_force | earlier_version_not_stored | not_found | act_not_in_store | repealed
    message: str
    quote_check: str | None = None  # identical | differs | None
    colour: str = "amber"
    source_url: str | None = None


# ---------------- Step 3: resolve ----------------

def _name_similarity(cur: psycopg.Cursor, name: str, title: str) -> float:
    cur.execute("SELECT similarity(%s, %s)", (name.lower(), title.lower()))
    return float(cur.fetchone()[0])  # type: ignore[index]


def resolve(conn: psycopg.Connection, item: CitedItem) -> list[Candidate]:
    out: list[Candidate] = []
    with conn.cursor() as cur:
        if item.citation:
            cur.execute("""SELECT c.id, c.title, c.court, c.year, c.decision_date, c.has_text, cc.origin
                           FROM case_citations cc JOIN cases c ON c.id = cc.case_id
                           WHERE cc.kind = %s AND cc.canonical = %s""", (item.citation.kind, item.citation.canonical))
            for r in cur.fetchall():
                sim = _name_similarity(cur, item.case_name, r[1]) if item.case_name else None
                out.append(Candidate(str(r[0]), r[1], r[2], r[3], str(r[4]) if r[4] else None, r[5], sim,
                                     "exact" if r[6] == "metadata" else "alias"))
        if not out and item.case_name:
            # Fuzzy: party names, year within +/-1 (also catches a wrong year)
            yr = item.year
            cur.execute("""SELECT id, title, court, year, decision_date, has_text, similarity(lower(title), %s) s
                           FROM cases WHERE lower(title) %% %s AND (%s::int IS NULL OR year BETWEEN %s - 3 AND %s + 3)
                           ORDER BY s DESC LIMIT 5""",
                        (item.case_name.lower(), item.case_name.lower(), yr, yr, yr))
            for r in cur.fetchall():
                if r[6] >= NAME_MATCH:
                    out.append(Candidate(str(r[0]), r[1], r[2], r[3], str(r[4]) if r[4] else None, r[5],
                                         float(r[6]), "name_year"))
    return out


# ---------------- Step 4: existence verdict ----------------

def verdict(item: CitedItem, cands: list[Candidate]) -> tuple[str, str]:
    if not cands:
        return "NOT_FOUND", "Not found in our corpus. This does not prove the case does not exist; the open corpus is incomplete."
    best = cands[0]
    if best.via in ("exact", "alias"):
        if item.case_name and best.name_similarity is not None and best.name_similarity < NAME_CONFLICT:
            return "CONFLICT", f"This citation belongs to a different case in our corpus: {best.title}."
        if best.via == "alias":
            return "PARTIAL", f"Matched {best.title} through a citation mined from other judgments (not official metadata)."
        if item.case_name and best.name_similarity is not None and best.name_similarity < NAME_MATCH:
            return "PARTIAL", f"Citation matches {best.title}, but the party names in the draft differ."
        return "VERIFIED", f"Citation matches {best.title} ({best.court}, {best.year})."
    # matched only by party names (+ year)
    if item.citation is not None:
        if item.year and best.year and abs(item.year - best.year) > 1:
            return "PARTIAL", (f"Party names match {best.title} ({best.year}), but the year {item.year} differs and "
                               f"the citation string was not found.")
        return "PARTIAL", (f"Party names and year match {best.title} ({best.year}), but this citation string "
                           f"({item.citation.canonical}) is not in our corpus; volume/page could not be confirmed.")
    if item.year and best.year and abs(item.year - best.year) > 1:
        return "PARTIAL", f"Party names match {best.title}, but it was decided in {best.year}, not {item.year}."
    return "VERIFIED", f"Party names and year match {best.title} ({best.court}, {best.year})."


# ---------------- Step 5: quotes ----------------

def case_body(conn: psycopg.Connection, case_id: str) -> tuple[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT role, string_agg(text, ' ' ORDER BY ord) FROM segments WHERE case_id=%s GROUP BY role",
                    (case_id,))
        parts: dict[str, str] = dict(cur.fetchall())
    return parts.get("body", ""), parts.get("headnote", "")


def check_quotes(conn: psycopg.Connection, item: CitedItem, best: Candidate | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for q in item.quotes:
        if best is None:
            out.append({"quote": q, "status": "not_checked", "reason": "Cited case not found, so the quote cannot be checked."})
            continue
        if not best.has_text:
            out.append({"quote": q, "status": "not_checked",
                        "reason": "The judgment text of this case is not in our corpus (metadata only)."})
            continue
        body, headnote = case_body(conn, best.case_id)
        m = find_quote(q, body)
        if m.status == "not_found" and headnote and find_quote(q, headnote).status != "not_found":
            out.append({"quote": q, "status": "only_in_headnote", "similarity": m.similarity,
                        "reason": "Found only in the SCR editorial headnote, not in the judgment itself."})
            continue
        out.append({"quote": q, "status": m.status, "similarity": m.similarity, "found_text": m.found_text,
                    "diff": m.diff})
    return out


# ---------------- Step 6: proposition (LLM judge) ----------------

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["supports", "partly_supports", "does_not_support", "contradicts"]},
        "quote": {"type": "string"},
        "passage_id": {"type": "integer"},
        "explanation": {"type": "string"},
    },
    "required": ["label", "quote", "passage_id", "explanation"],
    "additionalProperties": False,
}


async def check_proposition(conn: psycopg.Connection, llm: LLMProvider | None, item: CitedItem,
                            best: Candidate | None) -> dict[str, Any] | None:
    if best is None or not item.proposition or len(item.proposition) < 15:
        return None
    if not best.has_text:
        return {"label": "not_checked", "reason": "Judgment text not in corpus."}
    if llm is None:
        return {"label": "not_checked", "reason": "LLM disabled for this run."}
    passages = await asyncio.to_thread(search.case_passages, conn, best.case_id, item.proposition, 3)
    if not passages:
        return {"label": "not_checked", "reason": "No matching passage in the judgment."}
    prompt = (PROMPTS / "verification_judge_v1.md").read_text(encoding="utf-8")
    ctx = "\n\n".join(f"[passage {p.chunk_id}, page {p.page}]\n{p.text}" for p in passages)
    messages = [{"role": "system", "content": prompt},
                {"role": "user", "content": f"PROPOSITION:\n{item.proposition}\n\nPASSAGES FROM {best.title}:\n{ctx}"}]
    for attempt in range(4):  # free-tier rate limits: wait and retry rather than skip the check
        try:
            r = await llm.complete(messages, reasoning_effort="low", max_tokens=3000, json_schema=JUDGE_SCHEMA,
                                   schema_name="judgement")
            ans = json.loads(r.text)
            break
        except LLMUnavailable as e:
            if e.reason != "rate_limited" or attempt == 3:
                return {"label": "not_checked", "reason": f"AI judge unavailable: {e}"}
            await asyncio.sleep(min(e.retry_after_s or 4.0 * (attempt + 1), 20))
        except (LLMError, json.JSONDecodeError) as e:
            return {"label": "not_checked", "reason": f"AI judge gave no usable answer ({type(e).__name__})."}
    by_id = {p.chunk_id: p for p in passages}

    def contains(passage: str) -> bool:  # ignore spacing: PDF text often splits words ("presum ed")
        q = norm(ans["quote"]).replace(" ", "")
        return bool(q) and q in norm(passage).replace(" ", "")

    if not any(contains(p.text) for p in passages):  # spec 8 Step 6: no verifiable quote -> unsupported
        return {"label": "unsupported", "reason": "The AI judge could not quote supporting text from the judgment.",
                "model_label": ans["label"]}
    p = by_id.get(ans["passage_id"]) or next(p for p in passages if contains(p.text))
    if not contains(p.text):
        p = next(x for x in passages if contains(x.text))
    return {"label": ans["label"], "quote": ans["quote"], "explanation": ans["explanation"], "chunk_id": p.chunk_id,
            "page": p.page, "char_start": p.char_start, "char_end": p.char_end, "passage": p.text}


# ---------------- Step 7: good-law signal ----------------

def good_law(conn: psycopg.Connection, case_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT e.signal, c.title, c.year, e.sentence FROM citation_edges e
                       JOIN cases c ON c.id = e.citing_case_id
                       WHERE e.cited_case_id = %s AND e.signal IN ('overruled','per_incuriam','doubted','distinguished')
                       ORDER BY c.year DESC NULLS LAST LIMIT 10""", (case_id,))
        return [{"signal": r[0], "by": r[1], "year": r[2], "sentence": r[3]} for r in cur.fetchall()]


# ---------------- Step 8: statutes ----------------

def _repealed() -> list[dict[str, Any]]:
    return json.loads((RULES / "repealed_acts.json").read_text(encoding="utf-8"))["acts"]


def check_statute(conn: psycopg.Connection, ref: StatuteRef, relevant_date: date) -> StatuteResult:
    for act in _repealed():
        if re.search(act["pattern"], ref.act, re.I):
            rep = date.fromisoformat(act["repealed_on"])
            if relevant_date >= rep:
                return StatuteResult(ref.id, ref.raw, act["name"], ref.section, "repealed",
                                     f"{act['name']} was replaced by {act['replaced_by']} from {rep:%d-%m-%Y}; "
                                     f"for a date of {relevant_date:%d-%m-%Y} the new law applies (unverified rule).",
                                     colour="red")
            return StatuteResult(ref.id, ref.raw, act["name"], ref.section, "act_not_in_store",
                                 "This Act is not in the statute store yet; text not checked.", colour="amber")
    res = search.statute_as_on(conn, ref.act, ref.section, relevant_date)
    if res["status"] == "not_found":
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM acts WHERE short_name ILIKE %s OR title ILIKE %s", (ref.act, f"%{ref.act}%"))
            known = cur.fetchone() is not None
        status = "not_found" if known else "act_not_in_store"
        msg = f"Section {ref.section} does not exist in the stored {ref.act}." if known else \
            "This Act is not in the statute store yet; text not checked."
        return StatuteResult(ref.id, ref.raw, ref.act, ref.section, status, msg, colour="red" if known else "amber")
    quote_check = None
    if ref.quoted_text and res["text"]:
        quote_check = "identical" if norm(ref.quoted_text) in norm(res["text"]) else "differs"
    colour = "green" if res["status"] == "in_force" and quote_check != "differs" else \
        ("red" if res["status"] == "not_yet_in_force" or quote_check == "differs" else "amber")
    return StatuteResult(ref.id, ref.raw, res["act"], ref.section, res["status"], res["message"], quote_check,
                         colour, res["source_url"])


# ---------------- Steps 2-9 together ----------------

def _colour(r: CitationResult) -> str:
    if r.verdict == "CONFLICT" or any(q["status"] in ("not_found", "only_in_headnote") for q in r.quotes):
        return "red"
    if r.proposition and r.proposition.get("label") in ("contradicts", "does_not_support", "unsupported"):
        return "red"
    if r.verdict in ("PARTIAL", "NOT_FOUND") or any(q["status"] in ("near_exact", "not_checked") for q in r.quotes) \
            or (r.proposition and r.proposition.get("label") in ("partly_supports", "not_checked")) or r.good_law:
        return "amber"
    return "green"


async def verify(conn: psycopg.Connection, draft: str, llm: LLMProvider | None,
                 relevant_date: date | None = None) -> dict[str, Any]:
    relevant_date = relevant_date or date.today()
    items, refs = extract(draft)
    results: list[CitationResult] = []
    pending: list[tuple[CitationResult, CitedItem, Candidate | None]] = []
    for it in items:  # Steps 3-5 and 7: database lookups, in order
        cands = await asyncio.to_thread(resolve, conn, it)
        v, reason = verdict(it, cands)
        best = cands[0] if cands and v != "CONFLICT" else None
        r = CitationResult(it.id, it.raw, it.case_name, it.citation.canonical if it.citation else None, v, reason,
                           cands[:3], start=it.start, end=it.end, year=it.year)
        r.quotes = await asyncio.to_thread(check_quotes, conn, it, best)
        if best:
            r.good_law = await asyncio.to_thread(good_law, conn, best.case_id)
        pending.append((r, it, best))
        results.append(r)

    # Step 6: AI judge calls run concurrently (max 2 at once, within free-tier limits); the same case +
    # proposition is judged once.
    gate = asyncio.Semaphore(2)
    cache: dict[tuple[str, str], asyncio.Task[dict[str, Any] | None]] = {}

    async def judged(it: CitedItem, best: Candidate | None) -> dict[str, Any] | None:
        async with gate:
            return await check_proposition(conn, llm, it, best)

    for _r, it, best in pending:
        key = (best.case_id if best else "", it.proposition)
        if key not in cache:
            cache[key] = asyncio.create_task(judged(it, best))
    for r, it, best in pending:
        r.proposition = await cache[(best.case_id if best else "", it.proposition)]
        r.colour = _colour(r)
    statutes = [await asyncio.to_thread(check_statute, conn, ref, relevant_date) for ref in refs]
    blockers = [r.id for r in results if r.colour == "red"] + [s.id for s in statutes if s.colour == "red"]
    needs_ack = [r.id for r in results if r.colour == "amber"] + [s.id for s in statutes if s.colour == "amber"]
    return {
        "relevant_date": relevant_date.isoformat(),
        "release": "blocked" if blockers else ("needs_acknowledgement" if needs_ack else "clear"),
        "blocking_items": blockers,
        "items_needing_acknowledgement": needs_ack,
        "citations": [asdict(r) for r in results],
        "statutes": [asdict(s) for s in statutes],
        "notice": "Not legal advice. 'Not found' means not in our open-data corpus, not that a case is fake. "
                  "Good-law signals are heuristic. Nothing here was checked by a lawyer.",
    }
