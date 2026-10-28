"""Verified legal chat: redact -> retrieve -> answer only from sources -> verify every citation -> restore names.

The answer the user sees has passed through the same verifier as drafts (spec Section 8). Nothing is stored
except an audit entry; the conversation lives in the browser.
"""
import asyncio
import json
import re
from datetime import date
from typing import Any

import psycopg

from docketpilot.llm import LLMError, LLMProvider
from docketpilot.privacy import redact as pii
from docketpilot.retrieval import search as rs
from docketpilot.verification.engine import PROMPTS, verify

MAX_TURNS = 6
SECTION_REF = re.compile(r"\b(?:section|sec\.?|s\.|u/s\.?)\s*(\d{1,4}[A-Z]?)\b", re.I)


def _label(hit: dict[str, Any]) -> str:
    from docketpilot.agents.nodes import _case_label

    return _case_label(hit)


def _matter_context(conn: psycopg.Connection, matter_id: str, firm_id: Any) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT title FROM matters WHERE id=%s AND firm_id=%s", (matter_id, firm_id))
        m = cur.fetchone()
        if m is None:
            return None
        cur.execute("SELECT filename, redacted_text FROM matter_documents WHERE matter_id=%s ORDER BY created_at",
                    (matter_id,))
        docs = cur.fetchall()
        cur.execute("""SELECT checklist, similar_cases, id::text FROM drafts WHERE matter_id=%s AND checklist IS NOT NULL
                       ORDER BY version DESC LIMIT 1""", (matter_id,))
        d = cur.fetchone()
        cur.execute("SELECT title, due_date FROM reminders WHERE matter_id=%s ORDER BY due_date", (matter_id,))
        deadlines = [{"title": t, "due": str(due)} for t, due in cur.fetchall()]
    facts = None
    if d:
        try:
            from docketpilot.agents import graph

            facts = graph.current(d[2])["values"].get("facts")
        except Exception:  # facts are optional context
            facts = None
    return {"title": m[0], "documents": [{"file": f, "text": t[:6000]} for f, t in docs],
            "checklist": d[0] if d else None, "similar_cases": d[1] if d else None, "facts": facts,
            "deadlines": deadlines}


STYLE = {
    "simple": "\n\nSTYLE: Explain in plain, simple English that a first-year junior can follow. Put a short meaning "
              "in brackets the first time you use a legal term, e.g. 'cognizance (the court formally taking up the case)'.",
    "expert": "",
}
RISK_TASK = ("\n\nTASK: Give a risk assessment and strategy for this MATTER in the shape of rule 7, and add "
             "**Strategy to strengthen the case** with concrete steps (evidence to collect, defences to anticipate, "
             "deadlines to protect). Do not predict the result or give a probability.")


_TAG = r"(?:S:\w+|S\d+|P\d+)"
_TAG_RUN = re.compile(rf"\s*\[{_TAG}\](?:\s*\[{_TAG}\])*")


def statute_label(st: dict[str, Any]) -> str:
    """'Section 13, Hindu Marriage Act, 1955' -- the form the verifier recognises and checks."""
    act = re.sub(r"^The\s+", "", st["act_title"]).rstrip(".")
    return f"Section {st['section']}, {act}"


def statute_sources(conn: psycopg.Connection, text: str, query: str, default_act: str | None = None,
                    k: int = 4) -> list[dict[str, Any]]:
    """Statute sections for a question: every 'Section N of <Act>' mentioned (as in force today), then the
    sections whose wording best matches the question. Bare 'section 138' uses `default_act` when given."""
    from docketpilot.knowledge.statutes import act_title

    wanted: list[tuple[str, str]] = [(sr.act, sr.section) for sr in extract_refs(text)]
    if default_act:
        wanted += [(default_act, s.upper()) for s in SECTION_REF.findall(text)]
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for act, sec in wanted:
        if (act, sec) in seen or len(out) >= 5:
            continue
        seen.add((act, sec))
        st = rs.statute_as_on(conn, act, sec, date.today())
        if st["status"] != "not_found":
            out.append({"act": act, "act_title": st["act"] or act_title(act), "section": sec, "heading": st["heading"],
                        "text": st["text"] or st["message"], "status": st["status"]})
    for st in rs.statute_search(conn, query, k=k):
        if (st["act"], st["section"]) not in seen and len(out) < 7:
            seen.add((st["act"], st["section"]))
            out.append({**st, "status": "in_force"})
    for i, st in enumerate(out):
        st["tag"] = f"S{i + 1}"
        st["label"] = statute_label(st)
    return out


# Groq's free tier refuses any request above 8,000 tokens a minute, so the sources sent with one question are kept
# to about 16,000 characters (~4,500 tokens) on top of the prompt and conversation.
SOURCE_BUDGET_CHARS = 13_000


def fit_sources(passages: list[dict[str, Any]], statutes: list[dict[str, Any]],
                budget: int = SOURCE_BUDGET_CHARS) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Trim statute text first (sections mentioned by the user come first and are kept longest), then drop the
    weakest passages, until everything fits the budget."""
    statutes = [dict(s) for s in statutes[:5]]
    passages = [dict(p) for p in passages]
    for cap in (2500, 1600, 1000, 700):
        for s in statutes:
            s["text"] = (s.get("text") or "")[:cap]
        for p in passages:
            p["text"] = p["text"][:max(cap, 900)]
        if sum(len(s["text"]) for s in statutes) + sum(len(p["text"]) for p in passages) <= budget:
            break
    while passages and sum(len(s["text"]) for s in statutes) + sum(len(p["text"]) for p in passages) > budget:
        passages.pop()
    return passages, statutes


def extract_refs(text: str) -> list[Any]:
    from docketpilot.verification.extract import extract

    return extract(text)[1]


def swap_tags(text: str, labels: dict[str, str]) -> tuple[str, list[str]]:
    """Replace source tags with real citations. A run of tags "[P1][S2]" becomes one "(A; B)". The model sometimes
    writes 【P1】 instead of [P1]; both are accepted. Unknown tags are dropped. Nothing else in the text is touched.
    Statute tags are [S1], [S2] (labels given); the older [S:138] form means the NI Act."""
    text = re.sub(rf"【\s*({_TAG})\s*】", r"[\1]", text)
    used: list[str] = []

    def run(m: re.Match[str]) -> str:
        parts = []
        for tag in re.findall(rf"\[({_TAG})\]", m.group(0)):
            if tag.startswith("S:"):
                parts.append(f"Section {tag[2:]}, Negotiable Instruments Act, 1881")
            elif tag in labels:
                used.append(tag)
                parts.append(labels[tag])
        return f" ({'; '.join(dict.fromkeys(parts))})" if parts else ""

    return _TAG_RUN.sub(run, text), used


async def answer(conn: psycopg.Connection, llm: LLMProvider, messages: list[dict[str, str]],
                 matter_id: str | None = None, firm_id: Any = None, style: str = "expert",
                 mode: str = "answer") -> dict[str, Any]:
    turns = [m for m in messages if m.get("role") in ("user", "assistant") and m.get("content")][-MAX_TURNS:]
    if not turns or turns[-1]["role"] != "user":
        raise ValueError("last message must be from the user")

    # 1. Privacy: mask every turn before anything leaves the machine (earlier answers shown to the user carry
    # restored real names). One mapping for the whole request, so PERSON_1 stays the same person throughout.
    mapping: dict[str, str] = {}
    red_turns = []
    for t in turns:
        red = pii.redact(t["content"], mapping=mapping)
        mapping = red.mapping
        red_turns.append({"role": t["role"], "content": red.text})
    question = red_turns[-1]["content"]

    # 2. Retrieval: judgments (follow-ups borrow the previous question), statutes mentioned, matter context.
    prev_q = next((t["content"] for t in reversed(red_turns[:-1]) if t["role"] == "user"), "")
    query = question if len(question.split()) >= 6 or not prev_q else f"{prev_q} {question}"
    matter = _matter_context(conn, matter_id, firm_id) if matter_id else None
    if matter and matter.get("checklist"):  # ground matter questions in the law the checklist is about
        query += " " + " ".join(item["title"] for item in matter["checklist"][:4])
    res = rs.search(conn, query, rs.Filters(), mode="hybrid_rerank", k=12)
    passages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for h in res["hits"]:
        if h["case_id"] in seen or h["role"] != "body":
            continue
        seen.add(h["case_id"])
        passages.append({"tag": f"P{len(passages) + 1}", "chunk_id": h["chunk_id"], "case_id": h["case_id"],
                         "label": _label(h), "court": h["court"], "year": h["year"], "page": h["page"],
                         "text": h["text"][:1400]})
        if len(passages) == 6:
            break
    user_text = " ".join(t["content"] for t in red_turns if t["role"] == "user")
    statutes = statute_sources(conn, user_text, query, default_act="NI Act" if matter and matter.get("checklist") else None)
    passages, statutes = fit_sources(passages, statutes, SOURCE_BUDGET_CHARS - (6000 if matter else 0))

    src = "\n\n".join(f"[{p['tag']}] {p['court']}, {p['year']}:\n{p['text']}" for p in passages) or "(no passages found)"
    stat = "\n\n".join(f"[{st['tag']}] {st['label']} - {st.get('heading') or ''}:\n{(st['text'] or '')[:2500]}"
                       for st in statutes)
    ctx = f"SOURCES - JUDGMENTS:\n{src}\n\nSOURCES - STATUTES:\n{stat or '(none)'}"
    if matter:
        ctx += "\n\nMATTER (redacted):\n" + json.dumps({k: v for k, v in matter.items() if k != "similar_cases"},
                                                      default=str)[:6000]

    # 3. Answer only from the sources.
    system = (PROMPTS / "chat_v1.md").read_text(encoding="utf-8") + STYLE.get(style, "")
    if mode == "risk":
        system += RISK_TASK
        if matter and matter.get("similar_cases"):
            ctx += "\n\nSIMILAR PAST CASES (outcomes are heuristic signals):\n" + json.dumps(
                [{"case": s["label"], "court": s["court"], "year": s["year"], "outcome": s["outcome"]}
                 for s in matter["similar_cases"]])
    # earlier turns give context only: keep the last four, shortened, so the request stays under the token limit
    history = [{**t, "content": t["content"][:1500]} for t in red_turns[:-1][-4:]]
    convo = [{"role": "system", "content": system}, *history,
             {"role": "user", "content": f"{ctx}\n\nQUESTION:\n{question}"}]
    try:
        r = await llm.complete(convo, reasoning_effort="medium", max_tokens=6000)
    except LLMError:
        r = await llm.complete(convo, reasoning_effort="low", max_tokens=8000)
    text = r.text.strip()
    if not text:
        raise LLMError("empty answer")

    # 4. Replace source tags with real citations; unknown tags are dropped.
    labels = {p["tag"]: p["label"] for p in passages} | {st["tag"]: st["label"] for st in statutes}
    answer_red, used = swap_tags(text, labels)

    # 5. Verify everything in the answer (the same engine as drafts), then fix what failed: wrong citations
    # are corrected, unsupported ones are removed with the claim that relied on them.
    from docketpilot.verification.correct import autocorrect

    report = await verify(conn, answer_red, llm)
    answer_red, changes, report = await asyncio.to_thread(autocorrect, conn, answer_red, report)
    used = [t for t in used if labels[t] in answer_red]

    return {
        "answer": pii.restore(answer_red, mapping),
        "verification": report,
        "corrections": changes,
        "sources": [{k: p[k] for k in ("tag", "label", "chunk_id", "court", "year", "page")} | {"snippet": p["text"][:300]}
                    for p in passages if p["tag"] in used],
        "statutes": [{"label": st["label"], "heading": st.get("heading"), "source_url": st.get("source_url")}
                     for st in statutes if st["tag"] in used],
        "masked_items": len(mapping),
        "matter": matter["title"] if matter else None,
        "model": r.model,
    }
