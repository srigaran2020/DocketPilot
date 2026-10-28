"""Ask DocketPilot: one chat that routes to every feature.

Routing is rules first (spec 3.2: deterministic before LLM): schedule, draft, verify, similar cases,
risk & strategy, otherwise a verified answer. The only extra model call is reading a date out of a
scheduling command. Attachments use the normal preview/confirm upload endpoints from the browser.
"""
import asyncio
import json
import re
import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from docketpilot import audit, chat
from docketpilot.api.deps import CurrentUser, Session
from docketpilot.api.matters import _rows, launch_draft
from docketpilot.knowledge.citations import find_citations
from docketpilot.knowledge.pool import kb_conn
from docketpilot.llm import LLMError, LLMUnavailable, get_llm
from docketpilot.privacy import redact as pii
from docketpilot.retrieval import search as rs
from docketpilot.verification.engine import verify

router = APIRouter(tags=["assistant"])

# Documents an advocate drafts (any area of law).
DOC_WORDS = (r"(notice|complaint|petition|application|plaint|written\s+statement|reply|rejoinder|affidavit|appeal|"
             r"revision|agreement|deed|bail|vakalat|memo|counter|objection|caveat|synopsis|grounds|suit|letter|"
             r"undertaking|will|contract|lease|declaration|representation|submissions?)\b")

ROUTES: list[tuple[str, re.Pattern[str]]] = [
    # questions about dates are answered from the calendar, with no AI
    ("dates", re.compile(r"^\s*(?:when|what(?:'s| is| are)?|show(?: me)?|list|tell me)\b.{0,60}\b(?:hearings?|next\s+date|"
                         r"posting|dates?|deadlines?|calendar|schedule)\b(?!.*\b(?:on|for)\s+\d)", re.I)),
    ("schedule", re.compile(r"\b(remind(?:\s+me)?|reminder|schedule|add\s+(?:a\s+)?(?:hearing|date|deadline)|"
                            r"put\s+.*\bon\s+(?:my\s+)?calendar)\b", re.I)),
    ("draft", re.compile(r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+)?draft\b|"
                         rf"\b(draft|prepare|write|generate|make)\b.{{0,50}}\b{DOC_WORDS}", re.I)),
    ("verify", re.compile(r"\b(verify|validate|fact[- ]check|check\s+(?:these|this|the|my)\s+citations?|"
                          r"is\s+(?:this|it)\s+(?:a\s+)?(?:real|valid|genuine|fake))\b", re.I)),
    ("similar", re.compile(r"\b(similar|previous|past|related|earlier|comparable)\b.{0,30}\b(cases?|judgments?|"
                           r"decisions?|matters?)\b", re.I)),
    ("risk", re.compile(r"\b(strengths?|weakness(?:es)?|risks?|strategy|strategi[sz]e|chances?|win|defen[cs]es?|"
                        r"how\s+(?:strong|weak))\b", re.I)),
]


def route(text: str) -> str:
    for name, pattern in ROUTES:
        if pattern.search(text):
            return name
    if len(text) > 400 and len(find_citations(text)) >= 2:  # a pasted draft full of citations
        return "verify"
    return "answer"


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=60_000)


class AskIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=40)
    matter_id: str | None = None
    style: str = Field("expert", pattern="^(expert|simple)$")


def _matter_ok(conn: Any, matter_id: str, firm_id: Any) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id::text, title FROM matters WHERE id=%s AND firm_id=%s", (matter_id, firm_id))
        rows = _rows(cur)
    return rows[0] if rows else None


def resolve_matter(conn: Any, firm_id: Any, raw: str, selected: dict[str, Any] | None) -> tuple[dict[str, Any] | None, bool]:
    """Which case is the lawyer talking about? A case number or a party's real name in the message wins over
    the case file currently selected (names are matched locally against the encrypted vault)."""
    from docketpilot import casefile

    cn = casefile.find_case_number(raw)
    if cn:
        with conn.cursor() as cur:
            cur.execute("SELECT id::text, title FROM matters WHERE firm_id=%s AND facts->>'case_key'=%s LIMIT 1", (firm_id, cn.key))
            r = cur.fetchone()
        if r:
            return {"id": r[0], "title": r[1]}, not selected or selected["id"] != r[0]
    with conn.cursor() as cur:
        cur.execute("SELECT id::text, title, facts FROM matters WHERE firm_id=%s", (firm_id,))
        rows = cur.fetchall()
    low = raw.lower()
    hits = []
    for mid, title, facts in rows:
        names = casefile.names(mid)
        parties = [names.get((facts or {}).get(k) or "", "") for k in ("petitioner", "respondent")]
        if any(p and len(p) >= 4 and p.lower() in low for p in parties):
            hits.append({"id": mid, "title": title})
    if len(hits) == 1:
        return hits[0], not selected or selected["id"] != hits[0]["id"]
    return selected, False


def tool_dates(conn: Any, matter: dict[str, Any] | None, firm_id: Any) -> dict[str, Any]:
    """Upcoming dates straight from the calendar (no AI, so nothing can be invented)."""
    from docketpilot import casefile

    with conn.cursor() as cur:
        cur.execute("""SELECT r.title, r.due_date, r.rule_id, r.source, m.id::text, coalesce(m.case_number, m.title)
                       FROM reminders r JOIN matters m ON m.id=r.matter_id
                       WHERE m.firm_id=%s AND r.status='open' AND r.due_date >= current_date
                         AND (%s::uuid IS NULL OR m.id=%s::uuid)
                       ORDER BY r.due_date LIMIT 12""", (firm_id, matter["id"] if matter else None, matter["id"] if matter else None))
        rows = cur.fetchall()
    if not rows:
        where = f"for **{matter['title']}**" if matter else "in any case"
        return {"type": "message", "answer": f"No upcoming dates {where}. Attach the latest order or notice and I'll "
                                             "read the dates from it, or say \"Remind me of the hearing on …\"."}
    lines = []
    for title, due, rule, _source, mid, case in rows:
        names = casefile.names(mid)
        kind = "hearing" if (rule or "").startswith("doc-hearing") else ""
        lines.append(f"- **{due:%a %d %b %Y}** · {casefile.show(title, names)}" + ("" if matter else f" · {case}")
                     + (" ⚖" if kind else ""))
    head = f"Upcoming dates for **{matter['title']}**:" if matter else "Your upcoming dates across all cases:"
    return {"type": "dates", "answer": head + "\n" + "\n".join(lines) + "\n\nAll of these are on the Calendar page."}


def _new_matter(conn: Any, user: Any, title: str) -> str:
    mid = uuid.uuid4()
    conn.execute("INSERT INTO matters (id, firm_id, title, created_by) VALUES (%s,%s,%s,%s)",
                 (mid, user.firm_id, title, user.id))
    conn.commit()
    return str(mid)


# ---------------- tools ----------------

SCHEDULE_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "date": {"type": ["string", "null"]},
                   "warn_days_before": {"type": "integer"}},
    "required": ["title", "date", "warn_days_before"], "additionalProperties": False,
}


async def tool_schedule(conn: Any, text: str, matter_id: str) -> dict[str, Any]:
    masked = pii.redact(text, use_ner=False).text  # dates and titles only; no names needed
    today = date.today()
    try:
        r = await get_llm().complete(
            [{"role": "system", "content": "Extract a reminder from the advocate's command. Today is "
              f"{today.isoformat()} ({today:%A}). 'date' as YYYY-MM-DD (resolve words like 'next Monday'); null if no "
              "date is given. 'title': short, e.g. 'Hearing - cross-examination'. warn_days_before: 2 unless stated."},
             {"role": "user", "content": masked}],
            reasoning_effort="low", max_tokens=800, json_schema=SCHEDULE_SCHEMA, schema_name="reminder")
        ans = json.loads(r.text)
    except (LLMUnavailable, LLMError, json.JSONDecodeError) as e:
        return {"type": "message", "answer": f"I couldn't read a date from that ({type(e).__name__}). Try: "
                                             "\"Remind me of the hearing on 2026-11-05\"."}
    try:
        due = date.fromisoformat(str(ans.get("date"))[:10])
    except ValueError:
        # "Schedule the hearing" with no date: use the hearing date read from the papers, if there is one.
        with conn.cursor() as cur:
            cur.execute("""SELECT title, due_date, source FROM reminders WHERE matter_id=%s AND status='open'
                           AND due_date >= current_date AND rule_id LIKE 'doc-hearing%%' ORDER BY due_date LIMIT 1""",
                        (matter_id,))
            r = cur.fetchone()
        if r:
            return {"type": "scheduled", "reminder": {"title": r[0], "due": r[1].isoformat(),
                                                      "warn_on": (r[1] - timedelta(days=2)).isoformat()},
                    "answer": f"The next hearing is on **{r[1]:%A, %d %B %Y}** ({r[2]}). It's already on your calendar, "
                              "with a reminder two days before."}
        return {"type": "message", "answer": "I couldn't find a hearing date in this case's papers. Which date? "
                                             "For example: \"Hearing on 5 November 2026\"."}
    if due < today - timedelta(days=1):
        return {"type": "message", "answer": f"That date ({due:%d %b %Y}) is in the past. Did you mean a later year?"}
    warn = due - timedelta(days=max(0, int(ans.get("warn_days_before") or 2)))
    hearing = re.search(r"hearing|posting|next date|appearance", ans["title"] + " " + text, re.I)
    rid = f"doc-hearing-u{uuid.uuid4().hex[:8]}" if hearing else f"user-{uuid.uuid4().hex[:8]}"
    conn.execute("""INSERT INTO reminders (id, matter_id, rule_id, title, due_date, warn_on, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                 (uuid.uuid4(), matter_id, rid, ans["title"][:200], due, warn, "Added by you from Ask DocketPilot"))
    conn.commit()
    return {"type": "scheduled", "reminder": {"title": ans["title"], "due": due.isoformat(), "warn_on": warn.isoformat()},
            "answer": f"Scheduled **{ans['title']}** on **{due:%A, %d %B %Y}**, with a reminder from {warn:%d %b}. "
                      "It's on your Calendar."}


def tool_draft(conn: Any, user: Any, matter_id: str, text: str, background: BackgroundTasks) -> dict[str, Any]:
    """Cheque-bounce notices and complaints use the fixed s.138 templates; anything else is drafted from the
    request, the papers, the statute store and the judgment library (general workflow)."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM matter_documents WHERE matter_id=%s", (matter_id,))
        n_docs = cur.fetchone()[0]
    s138 = re.search(r"cheque|\b138\b|dishono", text, re.I)
    if s138 and n_docs and re.search(r"\bcomplaint\b", text, re.I):
        workflow, name = "complaint", "Section 138 complaint"
    elif s138 and n_docs and re.search(r"\bnotice\b", text, re.I) and not re.search(r"\breply\b", text, re.I):
        workflow, name = "demand_notice", "Section 138 demand notice"
    else:
        workflow, name = "general", doc_type_of(text)
    if workflow == "general" and not n_docs and len(text.split()) < 8:
        return {"type": "message", "answer": f"Tell me the facts for the **{name}** (who, what happened, when, what you "
                                             "want the court to do), or attach the case papers with 📎."}
    try:
        out = launch_draft(conn, user, matter_id, workflow, background, name if workflow == "general" else None,
                           text if workflow == "general" else None)
    except HTTPException as e:
        return {"type": "message", "answer": str(e.detail)}
    papers = f"{n_docs} paper(s)" + (" and your instructions" if workflow == "general" else "") if n_docs else "your instructions"
    return {"type": "draft_started", "draft_id": out["id"],
            "answer": f"Drafting the **{name}** from {papers}: reading the facts, finding the law, writing, and checking "
                      "every citation. This takes about a minute."}


def doc_type_of(text: str) -> str:
    """'Draft a bail application for my client ...' -> 'Bail application'."""
    m = re.search(r"\b(?:draft|prepare|write|generate|make)\s+(?:me\s+)?(?:an?\s+|the\s+)?(.{3,80}?)"
                  r"(?=\s+(?:for|against|on\s+behalf|under|in\s+the|in\s+case|seeking|to\s+the|regarding|about|based|from|"
                  r"with|where|as|which|that)\b|[,.:;\n]|$)", text, re.I)
    name = (m.group(1) if m else "legal document").strip()
    name = re.sub(r"^(?:a|an|the|my)\s+", "", name, flags=re.I)
    return (name[:1].upper() + name[1:])[:120] if name else "Legal document"


async def tool_verify(conn: Any, text: str) -> dict[str, Any]:
    body = re.sub(r"^\s*(please\s+)?(verify|check|validate)[^:\n]*[:\n]", "", text, flags=re.I).strip() or text
    from docketpilot.verification.correct import autocorrect

    red = pii.redact(body)
    report = await verify(conn, red.text, get_llm())
    fixed_text, changes, report = await asyncio.to_thread(autocorrect, conn, red.text, report)
    n = report.get("checked", 0)
    if not n:
        return {"type": "message", "answer": "I didn't find any case citations or section references to check in that text."}
    if not changes:
        return {"type": "verification", "verification": report, "corrections": [],
                "answer": f"**All {n} reference(s) check out.** Click any citation to see the passage it rests on."}
    return {"type": "verification", "verification": report, "corrections": changes,
            "corrected_text": pii.restore(fixed_text, red.mapping),
            "answer": f"I checked {n} reference(s) and **fixed {len(changes)}**. Here is the corrected text:"}


def tool_similar(conn: Any, text: str, matter: dict[str, Any] | None) -> dict[str, Any]:
    query = text
    if matter:
        with conn.cursor() as cur:
            cur.execute("SELECT similar_cases FROM drafts WHERE matter_id=%s AND similar_cases IS NOT NULL "
                        "ORDER BY version DESC LIMIT 1", (matter["id"],))
            row = cur.fetchone()
        if row and row[0]:
            return {"type": "similar", "cases": row[0],
                    "answer": f"Past judgments closest to **{matter['title']}**, with how they ended. "
                              "Outcomes are signals read from the judgments, not predictions."}
    from docketpilot.agents.nodes import _case_label

    res = rs.search(conn, pii.redact(query).text, rs.Filters(), mode="hybrid", k=25)
    cases, seen = [], set()
    with conn.cursor() as cur:
        for h in res["hits"]:
            if h["case_id"] in seen:
                continue
            seen.add(h["case_id"])
            cur.execute("SELECT outcome, outcome_confidence FROM cases WHERE id=%s", (h["case_id"],))
            oc = cur.fetchone()
            cases.append({"case_id": h["case_id"], "label": _case_label(h), "court": h["court"], "year": h["year"],
                          "outcome": oc[0] if oc else "unknown", "outcome_confidence": oc[1] if oc else 0,
                          "chunk_id": h["chunk_id"], "snippet": h["text"][:280]})
            if len(cases) == 6:
                break
    return {"type": "similar", "cases": cases,
            "answer": "Related past judgments, with how they ended. Outcomes are signals, not predictions."
            if cases else "I couldn't find related judgments in the library for that."}


# ---------------- endpoint ----------------

@router.post("/ask")
async def ask(body: AskIn, user: CurrentUser, session: Session, background: BackgroundTasks) -> dict[str, Any]:
    msgs = [m.model_dump() for m in body.messages]
    text = msgs[-1]["content"]
    if msgs[-1]["role"] != "user":
        raise HTTPException(422, "The last message must be yours")
    intent = route(text)  # juniors may draft too; approving a draft stays advocate-only

    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            from docketpilot.api.casefiles import case_card

            selected = _matter_ok(conn, body.matter_id, user.firm_id) if body.matter_id else None
            if body.matter_id and selected is None:
                raise HTTPException(404, "Case not found")
            matter, switched = resolve_matter(conn, user.firm_id, text, selected)
            created = None
            if intent in ("schedule", "draft") and matter is None:
                created = _new_matter(conn, user, f"New case · {date.today():%d %b %Y}")
                matter = {"id": created, "title": f"New case · {date.today():%d %b %Y}"}
            if matter:
                matter["title"] = case_card(conn, matter["id"])["label"]
            if intent == "dates":
                out = tool_dates(conn, matter, user.firm_id)
            elif intent == "schedule":
                out = asyncio.run(tool_schedule(conn, text, matter["id"]))  # type: ignore[index]
            elif intent == "draft":
                out = tool_draft(conn, user, matter["id"], text, background)  # type: ignore[index]
            elif intent == "verify":
                out = asyncio.run(tool_verify(conn, text))
            elif intent == "similar":
                out = tool_similar(conn, text, matter)
            else:
                mode = "risk" if intent == "risk" and matter else "answer"
                if intent == "risk" and matter is None:
                    msgs[-1]["content"] += ("\n\n(No case file is selected: answer generally about risks and strategy "
                                            "for this kind of case.)")
                out = asyncio.run(chat.answer(conn, get_llm(), msgs, matter["id"] if matter else None, user.firm_id,
                                              body.style, mode))
                out["type"] = "answer"
            out["intent"] = intent
            if matter:
                out["matter_id"], out["matter"] = matter["id"], matter["title"]
            out["created_matter"] = created
            out["switched_matter"] = bool(switched and matter)
            return out

    try:
        out = await asyncio.to_thread(run)
    except LLMUnavailable as e:
        when = "later" if (e.retry_after_s or 0) > 120 else "in a minute"
        raise HTTPException(503, f"The AI can't answer right now: {e}. Try again {when}. Meanwhile, Research (judgments "
                                 "and sections), the calendar, your cases and citation look-ups all work without AI.") from e
    except (LLMError, ValueError) as e:
        raise HTTPException(502, f"Could not produce a reliable answer: {e}") from e
    audit.record(session, "assistant.ask", actor_user_id=user.id, firm_id=user.firm_id,
                 details={"intent": intent, "matter": out.get("matter_id"), "style": body.style,
                          "release": (out.get("verification") or {}).get("release")})
    await session.commit()
    return out
