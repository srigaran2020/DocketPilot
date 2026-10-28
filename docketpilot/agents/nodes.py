"""Agent steps. Each takes the graph state and returns the fields it changes.

Model use: Document Analysis and Drafting call the LLM (redacted text only); Verification uses it for one
narrow step; Orchestrator, Research, Strategy & Risk and Monitoring are plain code (spec 7).
"""
import asyncio
import json
import re
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any, TypedDict

from docketpilot.knowledge.pool import kb_conn
from docketpilot.llm import LLMError, LLMResult, LLMUnavailable, get_llm, head_tail
from docketpilot.retrieval import search as rs
from docketpilot.rules import engine as rules
from docketpilot.verification.engine import verify
from docketpilot.verification.quotes import norm

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
OUTPUTS = Path(__file__).resolve().parents[2] / "data" / "outputs"

FACT_FIELDS = {
    "drawer": "person or firm who issued the cheque (placeholder)",
    "drawer_address": "drawer's address (placeholder)",
    "payee": "person or firm the cheque was issued to (placeholder)",
    "payee_bank_branch_city": "city of the payee's bank branch where the cheque was deposited",
    "drawee_bank": "bank the cheque was drawn on",
    "cheque_number": "cheque number",
    "cheque_date": "date written on the cheque",
    "amount": "cheque amount in rupees",
    "presentation_date": "date the cheque was presented/deposited",
    "return_reason": "reason in the bank's return memo",
    "return_information_date": "date the payee learned of the return / date of return memo",
    "notice_date": "date of the demand notice",
    "notice_received_date": "date the drawer received the notice",
    "payment_received": "whether the drawer paid after the notice (true/false)",
    "debt_description": "the debt or liability the cheque was for",
    "court_place": "place of the court, if stated",
}


class State(TypedDict, total=False):
    draft_id: str
    matter_id: str
    workflow: str  # demand_notice | complaint (s.138 templates) | general (any document, any area of law)
    doc_type: str  # general: what the advocate asked for, e.g. "Bail application"
    instructions: str  # general: the advocate's request, redacted
    documents: list[dict[str, Any]]  # [{id, filename, redacted_text}]
    facts: dict[str, Any]
    fact_sources: dict[str, Any]
    relevant_date: str
    research: dict[str, Any]
    sections: dict[str, str]
    draft_text: str
    verification: dict[str, Any]
    checklist: list[dict[str, Any]]
    similar_cases: list[dict[str, Any]]
    approval: dict[str, Any]
    status: str
    error: str | None
    trace: list[dict[str, Any]]


def _complete_json(messages: list[dict[str, str]], schema: dict[str, Any], name: str, effort: str,
                   max_tokens: int) -> tuple[dict[str, Any], LLMResult]:
    """gpt-oss can spend its whole budget on hidden reasoning and return nothing, which Groq reports as a JSON
    validation error. Retry once with low effort and a bigger budget."""
    llm = get_llm()
    attempts = [(effort, max_tokens), ("low", max_tokens + 4000)]
    last: Exception | None = None
    for eff, toks in attempts:
        try:
            r = asyncio.run(llm.complete(messages, reasoning_effort=eff, max_tokens=toks,  # type: ignore[arg-type]
                                         json_schema=schema, schema_name=name))
            return json.loads(r.text), r
        except (LLMError, json.JSONDecodeError) as e:
            last = e
    raise LLMError(f"no valid JSON after retry: {last}")


def _trace(state: State, node: str, t0: float, llm: LLMResult | None = None, **extra: Any) -> list[dict[str, Any]]:
    entry = {"node": node, "ms": int((time.perf_counter() - t0) * 1000), **extra}
    if llm:
        entry.update(model=llm.model, input_tokens=llm.input_tokens, output_tokens=llm.output_tokens)
    return [*state.get("trace", []), entry]


def save_draft(draft_id: str, **cols: Any) -> None:
    """Mirror progress into the drafts table so the UI can show it."""
    if not cols:
        return
    sets = ", ".join(f"{k} = %s" for k in cols)
    vals = [json.dumps(v, default=str) if isinstance(v, dict | list) else v for v in cols.values()]
    with kb_conn() as conn:
        conn.execute(f"UPDATE drafts SET {sets} WHERE id = %s", [*vals, draft_id])  # noqa: S608 (fixed column names)
        conn.commit()


# ---------- 1. Orchestrator (rules, no LLM) ----------

def orchestrator(state: State) -> State:
    t0 = time.perf_counter()
    wf = state.get("workflow") or "demand_notice"
    if wf not in ("demand_notice", "complaint", "general"):
        return {"status": "failed", "error": f"unknown workflow {wf}", "trace": _trace(state, "orchestrator", t0)}
    if wf == "general" and not (state.get("documents") or state.get("instructions")):
        return {"status": "failed", "error": "say what to draft, or attach the case papers",
                "trace": _trace(state, "orchestrator", t0)}
    if wf != "general" and not state.get("documents"):
        return {"status": "failed", "error": "no documents uploaded to this matter",
                "trace": _trace(state, "orchestrator", t0)}
    return {"workflow": wf, "status": "running", "error": None, "trace": _trace(state, "orchestrator", t0, workflow=wf)}


# ---------- 2. Document Analysis (LLM, schema-validated, quotes checked) ----------

def _extraction_schema() -> dict[str, Any]:
    field = {"type": "object", "properties": {"value": {"type": ["string", "number", "boolean", "null"]},
                                              "quote": {"type": ["string", "null"]}},
             "required": ["value", "quote"], "additionalProperties": False}
    return {"type": "object", "properties": {k: field for k in FACT_FIELDS}, "required": list(FACT_FIELDS),
            "additionalProperties": False}


def _general_analysis(state: State) -> State:
    """Any document type: a list of labelled facts, each kept only if its quote is in the papers or instructions."""
    t0 = time.perf_counter()
    docs = state.get("documents") or []
    instructions = state.get("instructions") or ""
    corpus = "\n\n".join(f"=== DOCUMENT {d['filename']} ===\n{d['redacted_text']}" for d in docs)
    fact = {"type": "object", "additionalProperties": False, "required": ["label", "value", "quote"],
            "properties": {"label": {"type": "string"}, "value": {"type": "string"}, "quote": {"type": "string"}}}
    schema = {"type": "object", "additionalProperties": False, "required": ["document_type", "facts"],
              "properties": {"document_type": {"type": "string"}, "facts": {"type": "array", "items": fact}}}
    try:
        raw, r = _complete_json(
            [{"role": "system", "content": (PROMPTS / "extraction_general_v1.md").read_text(encoding="utf-8")},
             {"role": "user", "content": f"INSTRUCTIONS:\n{instructions}\n\nDOCUMENTS:\n{head_tail(corpus) or '(none)'}"}],
            schema, "facts", "low", 5000)
    except (LLMUnavailable, LLMError) as e:
        return {"status": "failed", "error": f"AI step failed while reading the papers: {e}",
                "trace": _trace(state, "document_analysis", t0)}
    texts = [("instructions", norm(instructions))] + [(d["filename"], norm(d["redacted_text"])) for d in docs]
    facts: dict[str, Any] = {}
    sources: dict[str, Any] = {}
    rejected = []
    for f in raw.get("facts", [])[:25]:
        label, value, quote = str(f.get("label", "")).strip(), f.get("value"), f.get("quote") or ""
        where = next((name for name, t in texts if norm(quote) and norm(quote) in t), None)
        if not label or value in (None, "") or where is None:  # a fact must be written somewhere
            rejected.append(label)
            continue
        key = label if label not in facts else f"{label} ({len(facts)})"
        facts[key] = value
        sources[key] = {"document": where, "quote": quote}
    doc_type = state.get("doc_type") or raw.get("document_type") or "Legal document"
    return {"facts": facts, "fact_sources": sources, "doc_type": doc_type, "relevant_date": date.today().isoformat(),
            "trace": _trace(state, "document_analysis", t0, r, accepted=len(facts), rejected_no_source=rejected)}


def document_analysis(state: State) -> State:
    if state.get("workflow") == "general":
        return _general_analysis(state)
    t0 = time.perf_counter()
    docs = state["documents"]
    corpus = "\n\n".join(f"=== DOCUMENT {d['filename']} ===\n{d['redacted_text']}" for d in docs)
    fields = "\n".join(f"- {k}: {v}" for k, v in FACT_FIELDS.items())
    try:
        raw, r = _complete_json(
            [{"role": "system", "content": (PROMPTS / "extraction_v1.md").read_text(encoding="utf-8")},
             {"role": "user", "content": f"FIELDS:\n{fields}\n\nDOCUMENTS:\n{head_tail(corpus)}"}],
            _extraction_schema(), "facts", "low", 4000)
    except (LLMUnavailable, LLMError) as e:
        return {"status": "failed", "error": f"AI step failed during fact extraction: {e}",
                "trace": _trace(state, "document_analysis", t0)}
    facts: dict[str, Any] = {}
    sources: dict[str, Any] = {}
    normed = [(d, norm(d["redacted_text"])) for d in docs]
    rejected = []
    for k in FACT_FIELDS:
        item = raw.get(k) or {}
        value, quote = item.get("value"), item.get("quote")
        if value is None:
            continue
        hit = next((d for d, t in normed if quote and norm(quote) and norm(quote) in t), None)
        if hit is None:  # a fact without a findable source quote is not accepted (spec 7: facts carry their source)
            rejected.append(k)
            continue
        pos = hit["redacted_text"].find(quote) if quote in hit["redacted_text"] else 0
        facts[k] = value
        sources[k] = {"document": hit["filename"], "quote": quote, "page": hit["redacted_text"].count("\f", 0, pos) + 1}
    relevant = facts.get("return_information_date") or facts.get("cheque_date") or date.today().isoformat()
    return {"facts": facts, "fact_sources": sources, "relevant_date": str(relevant)[:10],
            "trace": _trace(state, "document_analysis", t0, r, accepted=len(facts), rejected_no_source=rejected)}


# ---------- 3. Research (code only) ----------

def _case_label(hit: dict[str, Any]) -> str:
    cits = hit.get("citations") or []
    title = re.sub(r"\s+", " ", hit["title"])
    m = re.search(r"\bof\s+(.*?)\s+Vs\.?\s+(.*)$", title, re.I) or re.search(r"^(.*?)\s+versus\s+(.*)$", title, re.I)
    name = f"{m.group(1).strip().title()} v. {m.group(2).strip().title()}" if m else title.title()
    name = re.sub(r"\s+(And|&)\s+(Another|Others|Ors\.?|Anr\.?)\b.*$", "", name, flags=re.I)
    own = next((c for c in cits if re.search(r"INSC|S\.?C\.?R|:[A-Z]+:", c)), None)
    return f"{name}, {own}" if own else f"{name} ({hit.get('year')})"


def _passages(hits: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for h in hits:
        if h["case_id"] in seen or h["role"] != "body":
            continue
        seen.add(h["case_id"])
        out.append({"tag": f"P{len(out) + 1}", "chunk_id": h["chunk_id"], "case_id": h["case_id"],
                    "label": _case_label(h), "court": h["court"], "year": h["year"], "page": h["page"],
                    "text": h["text"][:1500]})
        if len(out) == n:
            break
    return out


def _general_research(state: State) -> State:
    from docketpilot.chat import statute_sources

    t0 = time.perf_counter()
    fact_txt = " ".join(f"{k} {v}" for k, v in state.get("facts", {}).items())
    instructions = state.get("instructions") or ""
    query = f"{state.get('doc_type', '')} {instructions[:500]} {fact_txt[:500]}"
    with kb_conn() as conn:
        statutes = statute_sources(conn, f"{instructions} {fact_txt}", query, k=5)
        res = rs.search(conn, query, rs.Filters(), mode="hybrid_rerank", k=14)
    passages = _passages(res["hits"], 6)
    return {"research": {"statute_sections": statutes, "statutes": {}, "passages": passages, "query": query,
                         "search_mode": res["mode"], "notice": res["notice"]},
            "trace": _trace(state, "research", t0, passages=len(passages), statutes=len(statutes),
                            search_mode=res["mode"])}


def research(state: State) -> State:
    if state.get("workflow") == "general":
        return _general_research(state)
    t0 = time.perf_counter()
    on = date.fromisoformat(state.get("relevant_date") or date.today().isoformat())
    f = state.get("facts", {})
    query = " ".join(filter(None, ["dishonour of cheque section 138 notice", str(f.get("return_reason") or ""),
                                   "legally enforceable debt presumption section 139"]))
    with kb_conn() as conn:
        statutes = {s: rs.statute_as_on(conn, "NI Act", s, on) for s in ("138", "139", "142", "143A")}
        res = rs.search(conn, query, rs.Filters(s138_only=True), mode="hybrid_rerank", k=12)
    passages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for h in res["hits"]:
        if h["case_id"] in seen or h["role"] != "body":
            continue
        seen.add(h["case_id"])
        passages.append({"tag": f"P{len(passages) + 1}", "chunk_id": h["chunk_id"], "case_id": h["case_id"],
                         "label": _case_label(h), "court": h["court"], "year": h["year"], "page": h["page"],
                         "text": h["text"][:1500]})
        if len(passages) == 5:
            break
    return {"research": {"statutes": statutes, "passages": passages, "query": query, "search_mode": res["mode"],
                         "notice": res["notice"]},
            "trace": _trace(state, "research", t0, passages=len(passages), search_mode=res["mode"])}


# ---------- 4. Drafting (LLM fills designated sections only) ----------

def _general_drafting(state: State) -> State:
    from docketpilot.chat import fit_sources, swap_tags

    t0 = time.perf_counter()
    rsch = state["research"]
    facts = "\n".join(f"- {k}: {v}" for k, v in state.get("facts", {}).items())[:4000] or "(none)"
    # Groq free tier: one request must stay under 8,000 tokens, and the draft itself needs room to be written.
    budget = 9_000 - len(facts) - len(state.get("instructions") or "")
    passages, statutes = fit_sources(rsch["passages"], rsch["statute_sections"], max(budget, 4000))
    stat_txt = "\n\n".join(f"[{st['tag']}] {st['label']} - {st.get('heading') or ''}:\n{st['text']}"
                           for st in statutes) or "(none found)"
    pass_txt = "\n\n".join(f"[{p['tag']}] from a {p['court']} judgment ({p['year']}):\n{p['text']}"
                           for p in passages) or "(none found)"
    schema = {"type": "object", "properties": {"title": {"type": "string"}, "document": {"type": "string"}},
              "required": ["title", "document"], "additionalProperties": False}
    try:
        out, r = _complete_json(
            [{"role": "system", "content": (PROMPTS / "drafting_general_v1.md").read_text(encoding="utf-8")},
             {"role": "user", "content": f"DOCUMENT: {state.get('doc_type', 'Legal document')}\n\n"
                                         f"INSTRUCTIONS (redacted):\n{state.get('instructions') or '(none)'}\n\n"
                                         f"FACTS (redacted, from the papers):\n{facts}\n\n"
                                         f"STATUTE SECTIONS:\n{stat_txt}\n\nPASSAGES:\n{pass_txt}"}],
            schema, "document", "low", 6000)
    except (LLMUnavailable, LLMError) as e:
        return {"status": "failed", "error": f"AI step failed during drafting: {e}", "trace": _trace(state, "drafting", t0)}
    labels = {p["tag"]: p["label"] for p in rsch["passages"]} | {st["tag"]: st["label"] for st in rsch["statute_sections"]}
    text = swap_tags(out["document"].replace("\\n", "\n"), labels)[0]
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text).strip() + "\n"  # no markdown in a court document
    save_draft(state["draft_id"], redacted_text=text, research=rsch)
    return {"sections": {"title": out.get("title", "")}, "draft_text": text, "trace": _trace(state, "drafting", t0, r)}


def drafting(state: State) -> State:
    if state.get("workflow") == "general":
        return _general_drafting(state)
    from docketpilot.drafting import templates

    t0 = time.perf_counter()
    wf = state["workflow"]
    sections = templates.llm_sections(templates.load(wf))
    rsch = state["research"]
    stat_txt = "\n\n".join(f"[S:{k}] Section {k}, NI Act ({v['status']}):\n{v['text'] or v['message']}"
                           for k, v in rsch["statutes"].items())
    pass_txt = "\n\n".join(f"[{p['tag']}] from a {p['court']} judgment ({p['year']}):\n{p['text']}"
                           for p in rsch["passages"])
    schema = {"type": "object", "properties": {s: {"type": "string"} for s in sections}, "required": sections,
              "additionalProperties": False}
    try:
        out, r = _complete_json(
            [{"role": "system", "content": (PROMPTS / "drafting_v1.md").read_text(encoding="utf-8")},
             {"role": "user", "content": f"DOCUMENT TYPE: {wf}\nSECTIONS TO WRITE: {', '.join(sections)}\n\n"
                                         f"FACTS (redacted):\n{json.dumps(state.get('facts', {}), indent=1)}\n\n"
                                         f"STATUTE TEXT:\n{stat_txt}\n\nPASSAGES:\n{pass_txt}"}],
            schema, "sections", "medium", 10000)
    except (LLMUnavailable, LLMError) as e:
        return {"status": "failed", "error": f"AI step failed during drafting: {e}", "trace": _trace(state, "drafting", t0)}
    from docketpilot.chat import swap_tags

    labels = {p["tag"]: p["label"] for p in rsch["passages"]}
    # the model sometimes returns escaped newlines inside JSON strings; tags become real citations
    filled = {k: swap_tags(v.replace("\\n", "\n"), labels)[0] for k, v in out.items()}
    text = templates.fill(wf, state.get("facts", {}), filled)
    save_draft(state["draft_id"], redacted_text=text, research=rsch)
    return {"sections": filled, "draft_text": text, "trace": _trace(state, "drafting", t0, r)}


# ---------- 5. Verification (cannot be bypassed) ----------

def verification(state: State) -> State:
    t0 = time.perf_counter()
    from docketpilot.verification.correct import autocorrect

    try:
        with kb_conn() as conn:
            report = asyncio.run(verify(conn, state["draft_text"], get_llm(),
                                        date.fromisoformat(state.get("relevant_date") or date.today().isoformat())))
            # Fix what failed before the lawyer sees it: correct wrong citations, drop unsupported ones.
            text, changes, report = autocorrect(conn, state["draft_text"], report)
    except Exception as e:  # if verification fails, the draft cannot be released (spec 7)
        save_draft(state["draft_id"], status="failed")
        return {"status": "failed", "error": f"verification failed: {type(e).__name__}: {e}",
                "trace": _trace(state, "verification", t0)}
    save_draft(state["draft_id"], verification=report, redacted_text=text)
    return {"verification": report, "draft_text": text,
            "trace": _trace(state, "verification", t0, release=report["release"], corrected=len(changes))}


# ---------- 6. Strategy & Risk (rules + retrieval) ----------

_GAP = re.compile(r"\[(?:missing|NOT IN DOCUMENTS):\s*([^\]]+)\]", re.I)


def strategy_risk(state: State) -> State:
    t0 = time.perf_counter()
    facts = state.get("facts", {})
    general = state.get("workflow") == "general"
    if general:  # the checklist is what the draft still needs: every [missing: ...] gap
        gaps = list(dict.fromkeys(g.strip() for g in _GAP.findall(state.get("draft_text", ""))))
        check = [{"id": f"gap-{i + 1}", "title": f"Fill in: {g}", "status": "missing",
                  "evidence": "Not in the papers or instructions. Add it before filing.", "source": {}}
                 for i, g in enumerate(gaps)] or \
                [{"id": "complete", "title": "Every fact the draft needs was found in your papers", "status": "satisfied",
                  "evidence": "Still read each paragraph before filing.", "source": {}}]
        query, filters = state["research"]["query"], rs.Filters()
    else:
        check = rules.as_dicts(rules.checklist(facts))
        query = f"cheque dishonour {facts.get('return_reason') or ''} {facts.get('debt_description') or ''} section 138"
        filters = rs.Filters(s138_only=True)
    with kb_conn() as conn:
        res = rs.search(conn, query, filters, mode="hybrid", k=20)
        similar, seen = [], set()
        for h in res["hits"]:
            if h["case_id"] in seen:
                continue
            seen.add(h["case_id"])
            with conn.cursor() as cur:
                cur.execute("SELECT outcome, outcome_confidence FROM cases WHERE id=%s", (h["case_id"],))
                oc = cur.fetchone()
            similar.append({"case_id": h["case_id"], "label": _case_label(h), "court": h["court"], "year": h["year"],
                            "outcome": oc[0] if oc else "unknown", "outcome_confidence": oc[1] if oc else 0,
                            "chunk_id": h["chunk_id"], "snippet": h["text"][:300]})
            if len(similar) == 5:
                break
    status = "blocked" if state["verification"]["release"] == "blocked" else "awaiting_approval"
    save_draft(state["draft_id"], checklist=check, similar_cases=similar, status=status, trace=state.get("trace", []))
    return {"checklist": check, "similar_cases": similar, "status": status,
            "trace": _trace(state, "strategy_risk", t0, similar=len(similar))}


# ---------- 7. Monitoring (code only): reminders from the rule engine ----------

def monitoring(state: State) -> State:
    t0 = time.perf_counter()
    if state.get("workflow") == "general":  # dates come from the papers (casefile), not from s.138 rules
        return {"trace": _trace(state, "monitoring", t0, reminders=0)}
    dl = rules.deadlines(state.get("facts", {}))
    n = 0
    with kb_conn() as conn:
        for d in dl:
            if d.due is None:
                continue
            src = f"{d.source['act']} s.{d.source['section']} {d.source.get('clause', '')}: \"{d.source['quote']}\""
            conn.execute("""INSERT INTO reminders (id, matter_id, rule_id, title, due_date, warn_on, source)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (matter_id, rule_id) DO UPDATE
                            SET due_date = EXCLUDED.due_date, warn_on = EXCLUDED.warn_on""",
                         (uuid.uuid4(), state["matter_id"], d.id, d.title, d.due, d.warn_on, src))
            n += 1
        conn.commit()
    return {"trace": _trace(state, "monitoring", t0, reminders=n)}
