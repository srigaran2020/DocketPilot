"""Tiered retrieval (spec 6.1). Every hit carries case, chunk id and character offsets so the UI can
open the exact passage. Uses synchronous psycopg; the API calls these through a thread.

Tier 1  exact citation        -> case_citations lookup
Tier 2  statute as on a date  -> section_versions lookup
Tier 3  lexical               -> PostgreSQL full-text search (ts_rank_cd; a BM25-like ranking, not true BM25)
Tier 4  hybrid                -> lexical + dense (Qdrant), fused by reciprocal rank fusion
Tier 5  rerank                -> cross-encoder on the fused top-N
"""
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import psycopg
from qdrant_client import models as qm

from docketpilot.config import get_settings
from docketpilot.knowledge import citations as cit
from docketpilot.knowledge.statutes import AsOn, Footnote, ParsedSection, as_on


@dataclass
class Filters:
    court_level: str | None = None  # SC | HC
    year_from: int | None = None
    year_to: int | None = None
    s138_only: bool = False
    include_headnotes: bool = False  # headnotes are editorial; off by default


@dataclass
class Hit:
    chunk_id: int
    case_id: str
    title: str
    court: str
    year: int | None
    role: str
    page: int
    char_start: int
    char_end: int
    text: str
    citations: list[str] = field(default_factory=list)
    score: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)


# ---------------- Tier 1: exact citation ----------------

@dataclass
class CaseMatch:
    case_id: str
    title: str
    court: str
    year: int | None
    decision_date: date | None
    citation_kind: str
    canonical: str
    confidence: float
    origin: str


def lookup_citation(conn: psycopg.Connection, raw: str) -> list[CaseMatch]:
    c = cit.normalise(raw)
    if c is None:
        return []
    with conn.cursor() as cur:
        cur.execute("""SELECT cs.id, cs.title, cs.court, cs.year, cs.decision_date, cc.kind, cc.canonical,
                              cc.confidence, cc.origin
                       FROM case_citations cc JOIN cases cs ON cs.id = cc.case_id
                       WHERE cc.kind = %s AND cc.canonical = %s ORDER BY cc.confidence DESC""", (c.kind, c.canonical))
        return [CaseMatch(str(r[0]), *r[1:]) for r in cur.fetchall()]


# ---------------- Tier 2: statute as on date ----------------

def statute_as_on(conn: psycopg.Connection, act: str, section: str, on: date) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("""SELECT sv.section_number, sv.heading, sv.text, sv.footnotes, sv.inserted_on, sv.valid_from,
                              sv.source_url, sv.content_sha256, sv.status, a.title
                       FROM section_versions sv JOIN acts a ON a.id = sv.act_id
                       WHERE (a.short_name ILIKE %s OR a.title ILIKE %s) AND upper(sv.section_number) = upper(%s)""",
                    (act, f"%{act}%", section.strip()))
        row = cur.fetchone()
        notes: list[Footnote] = []
        if row:
            cur.execute("""SELECT note, action, amending_act, effective_date FROM amendments am
                           JOIN acts a ON a.id = am.act_id
                           WHERE (a.short_name ILIKE %s OR a.title ILIKE %s) AND upper(am.section_number) = upper(%s)
                           ORDER BY am.id""", (act, f"%{act}%", section.strip()))
            notes = [Footnote(*r) for r in cur.fetchall()]
    sec = None
    if row:
        sec = ParsedSection(number=row[0], heading=row[1], text=row[2], footnotes_raw=row[3], footnotes=notes,
                            inserted_on=row[4], valid_from=row[5], source_url=row[6], sha256=row[7])
    result: AsOn = as_on(sec, on)
    return {"act": row[9] if row else act, "section": section, "on": on.isoformat(), "status": result.status,
            "message": result.message, "text": result.text, "heading": sec.heading if sec else None,
            "source_url": sec.source_url if sec else None, "verification_status": row[8] if row else None,
            "amendments": [asdict(n) for n in notes]}


# Everyday names for provisions whose statutory wording is different (search help only, not legal text).
STATUTE_SYNONYMS = {
    r"anticipatory\s+bail": "bail apprehending arrest",
    r"\bquash\w*": "inherent powers high court",
    r"cheque\s+bounce": "dishonour cheque insufficiency funds",
    r"\bdivorce\b": "divorce dissolution marriage",
    r"\binjunction\b": "injunction restrain",
    r"\bFIR\b": "information cognizable offence",
    r"\balimony\b": "permanent alimony maintenance",
    r"\bcustody\b": "custody guardian minor",
    r"\bwill\b": "will testament",
}
_STATUTE_TSV = "to_tsvector('english', coalesce(sv.heading, '') || ' ' || coalesce(sv.text, ''))"


def statute_search(conn: psycopg.Connection, query: str, k: int = 4, acts: list[str] | None = None) -> list[dict[str, Any]]:
    """Sections whose heading/text best match the question (all stored Acts, or only `acts` by short name).
    Matches use the ix_section_versions_tsv index (migration 0004); words in the heading count more. A short query
    must match every word; if that finds too little, any word may match."""
    for pattern, extra in STATUTE_SYNONYMS.items():
        if re.search(pattern, query, re.I):
            query = f"{query} {extra}"
    act_filter = "AND a.short_name = ANY(%s)" if acts else ""
    sql = f"""SELECT a.short_name, a.title, sv.section_number, sv.heading, sv.text, sv.source_url, sv.status,
                     ts_rank_cd(setweight(to_tsvector('english', coalesce(sv.heading, '')), 'A')
                                || setweight(to_tsvector('english', coalesce(sv.text, '')), 'B'),
                                websearch_to_tsquery('english', %s)) AS rank
              FROM section_versions sv JOIN acts a ON a.id = sv.act_id
              WHERE {_STATUTE_TSV} @@ websearch_to_tsquery('english', %s) {act_filter} AND length(sv.text) > 40
              ORDER BY rank DESC LIMIT %s"""  # noqa: S608 (fixed fragments only)
    rows: list[Any] = []
    with conn.cursor() as cur:
        for tsq in dict.fromkeys([ts_text(query, max_words=4), ts_text(query, max_words=0)]):
            cur.execute(sql, [tsq, tsq, *([acts] if acts else []), k])
            rows += [r for r in cur.fetchall() if all((r[0], r[2]) != (x[0], x[2]) for x in rows)]
            if len(rows) >= k:
                break
    return [{"act": r[0], "act_title": r[1], "section": r[2], "heading": r[3], "text": r[4], "source_url": r[5],
             "verification_status": r[6]} for r in rows[:k]]


# ---------------- Tier 3: lexical ----------------

def ts_text(query: str, max_words: int = 6) -> str:
    """websearch_to_tsquery requires every word to match, so a long query (a sentence, a headnote) finds
    nothing. Long queries become an OR of their words; ts_rank_cd then favours chunks matching more of them."""
    words = re.findall(r"[A-Za-z0-9]+", query)
    return " or ".join(words[:80]) if len(words) > max_words else query

def _where(f: Filters, alias: str = "c", chunk_alias: str = "ch") -> tuple[str, list[Any]]:
    parts: list[str] = []
    args: list[Any] = []
    if f.court_level:
        parts.append(f"{alias}.court_level = %s")
        args.append(f.court_level)
    if f.year_from:
        parts.append(f"{alias}.year >= %s")
        args.append(f.year_from)
    if f.year_to:
        parts.append(f"{alias}.year <= %s")
        args.append(f.year_to)
    if f.s138_only:
        parts.append(f"{alias}.is_s138")
    if not f.include_headnotes:
        parts.append(f"{chunk_alias}.role <> 'headnote'")
    return (" AND " + " AND ".join(parts)) if parts else "", args


def lexical(conn: psycopg.Connection, query: str, f: Filters, k: int = 50) -> list[tuple[int, float]]:
    where, args = _where(f)
    with conn.cursor() as cur:
        cur.execute(f"""SELECT ch.id, ts_rank_cd(ch.tsv, q, 32) AS r
                        FROM chunks ch JOIN cases c ON c.id = ch.case_id,
                             websearch_to_tsquery('english', %s) q
                        WHERE ch.tsv @@ q {where} ORDER BY r DESC LIMIT %s""",  # noqa: S608 (where is built from fixed parts)
                    [ts_text(query), *args, k])
        return [(int(r[0]), float(r[1])) for r in cur.fetchall()]


# ---------------- dense ----------------

def dense(query: str, f: Filters, k: int = 50) -> list[tuple[int, float]]:
    from docketpilot.retrieval.index import client
    from docketpilot.retrieval.models import embed_query

    must: list[qm.Condition] = []
    must_not: list[qm.Condition] = []
    if f.court_level:
        must.append(qm.FieldCondition(key="court_level", match=qm.MatchValue(value=f.court_level)))
    if f.year_from or f.year_to:
        must.append(qm.FieldCondition(key="year", range=qm.Range(gte=f.year_from, lte=f.year_to)))
    if f.s138_only:
        must.append(qm.FieldCondition(key="is_s138", match=qm.MatchValue(value=True)))
    if not f.include_headnotes:
        must_not.append(qm.FieldCondition(key="role", match=qm.MatchValue(value="headnote")))
    res = client().query_points(get_settings().qdrant_collection, query=embed_query(query), limit=k,
                                query_filter=qm.Filter(must=must or None, must_not=must_not or None),
                                search_params=qm.SearchParams(quantization=qm.QuantizationSearchParams(rescore=True)))
    return [(int(p.id), float(p.score)) for p in res.points]


# ---------------- fusion, hydration, rerank ----------------

def rrf(*rankings: list[tuple[int, float]], k: int = 60) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, (doc, _) in enumerate(ranking):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


def hydrate(conn: psycopg.Connection, ranked: list[tuple[int, float]]) -> list[Hit]:
    if not ranked:
        return []
    ids = [i for i, _ in ranked]
    with conn.cursor() as cur:
        cur.execute("""SELECT ch.id, ch.case_id, c.title, c.court, c.year, ch.role, ch.page, ch.char_start,
                              ch.char_end, ch.text,
                              (SELECT array_agg(cc.raw ORDER BY cc.kind) FROM case_citations cc WHERE cc.case_id = c.id)
                       FROM chunks ch JOIN cases c ON c.id = ch.case_id WHERE ch.id = ANY(%s)""", (ids,))
        rows = {r[0]: r for r in cur.fetchall()}
    out = []
    for i, s in ranked:
        r = rows.get(i)
        if r:
            out.append(Hit(r[0], str(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], list(r[10] or []), s))
    return out


def search(conn: psycopg.Connection, query: str, f: Filters | None = None, mode: str = "hybrid_rerank",
           k: int = 10, pool: int = 50) -> dict[str, Any]:
    """mode: lexical | dense | hybrid | hybrid_rerank. Falls back to lexical if the vector index is down
    (spec 6.4, point 3)."""
    f = f or Filters()
    timings: dict[str, float] = {}
    notice = None
    t = time.perf_counter()
    lex = lexical(conn, query, f, pool) if mode != "dense" else []
    timings["lexical_ms"] = (time.perf_counter() - t) * 1000
    den: list[tuple[int, float]] = []
    if mode != "lexical":
        t = time.perf_counter()
        try:
            den = dense(query, f, pool)
        except Exception as e:  # vector store or model unavailable -> lexical only, and say so
            notice = f"Vector search unavailable ({type(e).__name__}); showing keyword results only."
            mode = "lexical"
        timings["dense_ms"] = (time.perf_counter() - t) * 1000
    if mode == "lexical":
        fused = lex
    elif mode == "dense":
        fused = den
    else:
        fused = rrf(lex, den)
    hits = hydrate(conn, fused[: pool if mode == "hybrid_rerank" else k])
    if mode == "hybrid_rerank" and hits:
        from docketpilot.retrieval.models import rerank_scores

        t = time.perf_counter()
        for h, s in zip(hits, rerank_scores(query, [h.text for h in hits]), strict=True):
            h.scores["fused"] = h.score
            h.score = s
        hits.sort(key=lambda h: -h.score)
        timings["rerank_ms"] = (time.perf_counter() - t) * 1000
    return {"query": query, "mode": mode, "notice": notice, "timings": timings,
            "hits": [asdict(h) for h in hits[:k]]}


def case_passages(conn: psycopg.Connection, case_id: str | uuid.UUID, query: str, k: int = 3) -> list[Hit]:
    """Best-matching body passages of one case (used by verification, Step 6)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT ch.id, ts_rank_cd(ch.tsv, websearch_to_tsquery('english', %s), 32) r
                       FROM chunks ch WHERE ch.case_id = %s AND ch.role = 'body' ORDER BY r DESC LIMIT %s""",
                    (ts_text(query, max_words=3), case_id, k))
        ranked = [(int(r[0]), float(r[1])) for r in cur.fetchall()]
    return hydrate(conn, ranked)
