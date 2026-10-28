"""Research and verification endpoints. Knowledge-base queries run in a worker thread (sync psycopg)."""
import asyncio
from dataclasses import asdict
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from docketpilot import audit
from docketpilot.api.deps import CurrentUser, Session
from docketpilot.knowledge.pool import kb_conn
from docketpilot.llm import get_llm
from docketpilot.retrieval import search as rs
from docketpilot.verification.engine import verify

router = APIRouter(tags=["research"])


@router.get("/search")
async def search_endpoint(
    user: CurrentUser, session: Session,
    q: str = Query(min_length=2, max_length=500),
    mode: str = Query("hybrid_rerank", pattern="^(lexical|dense|hybrid|hybrid_rerank)$"),
    court_level: str | None = Query(None, pattern="^(SC|HC)$"),
    year_from: int | None = None, year_to: int | None = None,
    s138_only: bool = False, k: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    f = rs.Filters(court_level, year_from, year_to, s138_only)

    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            return rs.search(conn, q, f, mode, k)

    result = await asyncio.to_thread(run)
    audit.record(session, "research.search", actor_user_id=user.id, firm_id=user.firm_id,
                 details={"mode": result["mode"], "hits": len(result["hits"])})
    await session.commit()
    return result


@router.get("/citations/lookup")
async def citation_lookup(user: CurrentUser, c: str = Query(min_length=4, max_length=200)) -> dict[str, Any]:
    def run() -> list[rs.CaseMatch]:
        with kb_conn() as conn:
            return rs.lookup_citation(conn, c)

    matches = await asyncio.to_thread(run)
    return {"query": c, "found": bool(matches), "matches": [asdict(m) for m in matches]}


@router.get("/acts")
async def acts(user: CurrentUser) -> list[dict[str, Any]]:
    """The Acts in the statute store, for pickers."""
    def run() -> list[dict[str, Any]]:
        with kb_conn() as conn, conn.cursor() as cur:
            cur.execute("""SELECT a.short_name, a.title, count(sv.id) FROM acts a LEFT JOIN section_versions sv ON sv.act_id=a.id
                           GROUP BY a.id ORDER BY a.title""")
            return [{"short_name": r[0], "title": r[1], "sections": r[2]} for r in cur.fetchall()]

    return await asyncio.to_thread(run)


@router.get("/statutes/search")
async def statutes_search(user: CurrentUser, q: str = Query(min_length=2, max_length=300),
                          act: str | None = None) -> list[dict[str, Any]]:
    """Sections by topic ("anticipatory bail", "divorce cruelty"), across every stored Act."""
    def run() -> list[dict[str, Any]]:
        with kb_conn() as conn:
            return rs.statute_search(conn, q, k=8, acts=[act] if act else None)

    return await asyncio.to_thread(run)


@router.get("/statutes/{act}/{section}")
async def statute(user: CurrentUser, act: str, section: str, on: date | None = None) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            return rs.statute_as_on(conn, act, section, on or date.today())

    return await asyncio.to_thread(run)


@router.get("/cases/{case_id}")
async def case_detail(user: CurrentUser, case_id: str) -> dict[str, Any]:
    def run() -> dict[str, Any] | None:
        with kb_conn() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id, title, court, court_level, year, decision_date, judges, outcome,
                                  outcome_confidence, is_s138, has_text, source, source_key, licence
                           FROM cases WHERE id = %s""", (case_id,))
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d.name for d in cur.description or []]
            case = dict(zip(cols, row, strict=True))
            cur.execute("SELECT kind, raw, origin, confidence FROM case_citations WHERE case_id=%s", (case_id,))
            case["citations"] = [dict(zip(("kind", "raw", "origin", "confidence"), r, strict=True))
                                 for r in cur.fetchall()]
            cur.execute("SELECT role, char_start, char_end FROM segments WHERE case_id=%s ORDER BY ord", (case_id,))
            case["segments"] = [dict(zip(("role", "char_start", "char_end"), r, strict=True)) for r in cur.fetchall()]
            return case

    case = await asyncio.to_thread(run)
    if case is None:
        raise HTTPException(404, "Case not found")
    return case


@router.get("/chunks/{chunk_id}")
async def chunk_passage(user: CurrentUser, chunk_id: int) -> dict[str, Any]:
    """The exact stored passage behind a citation badge, with its neighbours for context."""
    def run() -> dict[str, Any] | None:
        with kb_conn() as conn, conn.cursor() as cur:
            cur.execute("""SELECT ch.case_id, ch.ord, ch.role, ch.page, ch.text, c.title, c.court, c.year
                           FROM chunks ch JOIN cases c ON c.id = ch.case_id WHERE ch.id = %s""", (chunk_id,))
            r = cur.fetchone()
            if r is None:
                return None
            cur.execute("SELECT text FROM chunks WHERE case_id=%s AND ord IN (%s, %s) ORDER BY ord",
                        (r[0], r[1] - 1, r[1] + 1))
            around = [x[0] for x in cur.fetchall()]
            return {"chunk_id": chunk_id, "case_id": str(r[0]), "role": r[2], "page": r[3], "text": r[4],
                    "title": r[5], "court": r[6], "year": r[7], "context": around}

    p = await asyncio.to_thread(run)
    if p is None:
        raise HTTPException(404, "Passage not found")
    return p


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    matter_id: str | None = None


@router.post("/chat")
async def chat_endpoint(body: ChatRequest, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Verified chat: names masked before the AI sees them, answers only from retrieved sources, every
    citation in the answer verified."""
    from docketpilot import chat
    from docketpilot.llm import LLMError, LLMUnavailable

    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            return asyncio.run(chat.answer(conn, get_llm(), [m.model_dump() for m in body.messages],
                                           body.matter_id, user.firm_id))

    try:
        out = await asyncio.to_thread(run)
    except LLMUnavailable as e:
        raise HTTPException(503, f"The AI is unavailable right now ({e}). Search and verification still work.") from e
    except (LLMError, ValueError) as e:
        raise HTTPException(502, f"Could not produce a reliable answer: {e}") from e
    audit.record(session, "chat.ask", actor_user_id=user.id, firm_id=user.firm_id,
                 details={"turns": len(body.messages), "matter": body.matter_id, "masked": out["masked_items"],
                          "release": out["verification"]["release"], "sources": len(out["sources"])})
    await session.commit()
    return out


class VerifyRequest(BaseModel):
    text: str = Field(min_length=10, max_length=100_000)
    relevant_date: date | None = None
    use_llm: bool = True


@router.post("/verify")
async def verify_endpoint(body: VerifyRequest, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Standalone verification (spec 17, Phase 5). The text must already be redacted if it holds client data."""
    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            return asyncio.run(verify(conn, body.text, get_llm() if body.use_llm else None, body.relevant_date))

    report = await asyncio.to_thread(run)
    audit.record(session, "verification.run", actor_user_id=user.id, firm_id=user.firm_id,
                 details={"release": report["release"], "citations": len(report["citations"]),
                          "statutes": len(report["statutes"]), "llm": body.use_llm})
    await session.commit()
    return report
