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
                       WHERE (a.short_name ILIKE %s OR a.title ILIKE %s) AND upper(sv.section_number) = upper(%s)
                       ORDER BY (sv.valid_to IS NOT NULL AND coalesce(sv.valid_from, '0001-01-01') <= %s
                                 AND %s < sv.valid_to) DESC,  -- an earlier stored version in force on that date first
                                (sv.valid_to IS NULL) DESC, sv.valid_from DESC NULLS LAST
                       LIMIT 1""",
                    (act, f"%{act}%", section.strip(), on, on))
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
    r"\bwom[ae]n\b|\bempower": "women woman wife female girl dowry harassment",
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
_TITLE_TSV = "to_tsvector('english', a.title)"
# Words that say how to answer, not what the law is about ("top 10 best laws"); left in, "10" alone matched GST.
_FILLER = re.compile(r"\b(?:talk|tell|about|explain|describe|give|provide|list|name|show|me|us|please|top|best|most|"
                     r"important|key|main|major|some|all|any|various|different|which|what|are|is|the|a|an|of|on|in|for|"
                     r"and|or|to|with|from|by|can|could|should|would|do|does|did|i|you|we|it|this|that|these|those|why|"
                     r"how|only|just|few|more|need|want|asked|provided|dont|not|no|yes|ok|okay|laws?|acts?|statutes?|"
                     r"legislations?|provisions?|rules?|india|indian|central|ten|five|\d+)\b", re.I)


# Sections that say nothing about the law itself: never offered as the answer.
BOILERPLATE = re.compile(r"\s*(?:\[?repealed|\[?omitted|omitted|short title|repeal and savings?|savings|"
                         r"application of this chapter|power to (?:make|remove) (?:rules|difficult)|power to frame schemes|"
                         r"act not in derogation|act to be in addition|protection of action taken|"
                         r"act to have overriding|commencement)", re.I)


def long_title(about: str | None) -> str:
    """The Act's official long title ("An Act to provide for ...") from acts.about, or ''."""
    m = re.search(r"(An Act (?:to|for)\b.*?\.)(?:\s|$)", about or "", re.S)
    return m.group(1) if m else ""


def statute_words(query: str) -> str:
    """The topic words of a statute question ("top 10 best women empowerment laws" -> "women empowerment")."""
    words = _FILLER.sub(" ", query).split()
    return " ".join(words) if words else query


def statute_search(conn: psycopg.Connection, query: str, k: int = 4, acts: list[str] | None = None,
                   per_act: int | None = None) -> list[dict[str, Any]]:
    """Sections that best answer the question (all stored Acts, or only `acts` by short name).

    Hybrid, like judgment search: keyword matches (the Act's title and the section heading count most) and
    meaning matches from the `statutes` vector index are fused, then the cross-encoder re-ranks the top
    candidates against the question. "Short title" sections are skipped (they say nothing about the law).
    per_act: at most that many sections from one Act (for "which laws deal with X" questions)."""
    from docketpilot.retrieval import statute_index
    from docketpilot.retrieval.models import rerank_scores

    topic = statute_words(query)
    expanded = topic
    for pattern, extra in STATUTE_SYNONYMS.items():
        if re.search(pattern, topic, re.I):
            expanded = f"{expanded} {extra}"
    act_filter = "AND a.short_name = ANY(%s)" if acts else ""
    sql = f"""SELECT sv.id FROM section_versions sv JOIN acts a ON a.id = sv.act_id
              WHERE ({_STATUTE_TSV} @@ websearch_to_tsquery('english', %s) OR {_TITLE_TSV} @@ websearch_to_tsquery('english', %s))
                    {act_filter} AND length(sv.text) > 40 AND sv.valid_to IS NULL
              ORDER BY ts_rank_cd(setweight({_TITLE_TSV}, 'A')
                                  || setweight(to_tsvector('english', coalesce(sv.heading, '')), 'A')
                                  || setweight(to_tsvector('english', coalesce(sv.text, '')), 'B'),
                                  websearch_to_tsquery('english', %s)) DESC
              LIMIT %s"""  # noqa: S608 (fixed fragments only)
    pool = 80 if per_act else 40  # a list of Acts needs a wide pool to find many different Acts
    lexical_ids: list[int] = []
    with conn.cursor() as cur:
        for tsq in dict.fromkeys([ts_text(expanded, max_words=4), ts_text(expanded, max_words=0)]):
            cur.execute(sql, [tsq, tsq, *([acts] if acts else []), tsq, pool])
            lexical_ids += [r[0] for r in cur.fetchall() if r[0] not in lexical_ids]
            if len(lexical_ids) >= pool // 2:
                break
    dense_ids = statute_index.dense(topic, k=pool, acts=acts)
    fused = [i for i, _ in rrf([(i, 0.0) for i in lexical_ids], [(i, 0.0) for i in dense_ids])][:pool]
    if not fused:
        return []
    with conn.cursor() as cur:
        cur.execute("""SELECT sv.id, a.short_name, a.title, sv.section_number, sv.heading, sv.text, sv.source_url, sv.status
                       FROM section_versions sv JOIN acts a ON a.id = sv.act_id WHERE sv.id = ANY(%s)""", (fused,))
        by_id = {r[0]: r for r in cur.fetchall()}
    cands = [by_id[i] for i in fused if i in by_id and not BOILERPLATE.match(by_id[i][4] or "")][:40]
    try:  # the cross-encoder reads question and section together; fall back to fused order if it is unavailable
        scores = rerank_scores(topic, [f"{r[2]}. {r[4]}. {r[5][:600]}" for r in cands])
        cands = [r for _, r in sorted(zip(scores, cands, strict=True), key=lambda x: -x[0])]
    except Exception:  # noqa: S110 (ranking quality only)
        pass
    # a section whose heading is exactly the topic ("Theft." for "punishment for theft") comes first
    words = set(re.findall(r"[a-z]+", topic.lower()))

    def named(r: Any) -> bool:
        h = re.sub(r"^(?:punishment for|definition of)\s+", "", re.sub(r"[^a-z ]", "", (r[4] or "").lower()).strip())
        return bool(h) and set(h.split()) <= words
    cands = [r for r in cands if named(r)] + [r for r in cands if not named(r)]
    rows: list[Any] = []
    per: dict[str, int] = {}
    for r in cands:
        if per_act and per.get(r[1], 0) >= per_act:
            continue
        per[r[1]] = per.get(r[1], 0) + 1
        rows.append(r)
        if len(rows) >= k:
            break
    return [{"act": r[1], "act_title": r[2], "section": r[3], "heading": r[4], "text": r[5], "source_url": r[6],
             "verification_status": r[7]} for r in rows]


def statute_list(conn: psycopg.Connection, query: str, k: int = 10) -> list[dict[str, Any]]:
    """For "which laws deal with X": rank whole Acts, then give each chosen Act's best section.

    Two rankings are fused: the cross-encoder reading each Act's title and India Code description (acts.about)
    against the topic, and the order in which Acts appear among the best-matching sections. Picking the ten best
    sections and keeping one per Act let unrelated Acts in through single stray sections."""
    from docketpilot.retrieval.models import rerank_scores

    topic = statute_words(query)
    with conn.cursor() as cur:
        cur.execute("SELECT short_name, title || '. ' || coalesce(about, '') FROM acts WHERE EXISTS "
                    "(SELECT 1 FROM section_versions sv WHERE sv.act_id = acts.id AND sv.valid_to IS NULL)")
        acts = cur.fetchall()
    scores = rerank_scores(topic, [t[:900] for _, t in acts])
    by_title = [a for (a, _), _ in sorted(zip(acts, scores, strict=True), key=lambda x: -x[1])]
    sections: list[dict[str, Any]] = statute_search(conn, query, k=30, per_act=2)
    by_sections = list(dict.fromkeys(s["act"] for s in sections))
    relevant = set(by_title[:15])  # an Act must be about the topic, not just contain one matching section
    fused = [a for a, _ in rrf([(a, 0.0) for a in by_title[:25]], [(a, 0.0) for a in by_sections]) if a in relevant][:k]
    out: list[dict[str, Any]] = []
    from docketpilot.retrieval import statute_index

    about: dict[str, str] = dict(acts)
    picks: dict[str, list[int]] = {}
    for act in fused:
        # the section that best shows what the Act does: nearest in meaning to the topic plus the Act's long title
        purpose = re.split(r"(?<=\.)\s", about.get(act, ""), maxsplit=2)
        ids = statute_index.dense(f"{topic}. {' '.join(purpose[:1])}", k=6, acts=[act])
        if ids:
            picks[act] = ids
    with conn.cursor() as cur:
        cur.execute("""SELECT sv.id, a.short_name, a.title, sv.section_number, sv.heading, sv.text, sv.source_url, sv.status
                       FROM section_versions sv JOIN acts a ON a.id = sv.act_id WHERE sv.id = ANY(%s)""",
                    ([i for ids in picks.values() for i in ids],))
        got = {r[0]: r for r in cur.fetchall()}
    for act in fused:
        r = next((got[i] for i in picks.get(act, []) if i in got and not BOILERPLATE.match(got[i][4] or "")), None)
        best = ({"act": r[1], "act_title": r[2], "section": r[3], "heading": r[4], "text": r[5], "source_url": r[6],
                 "verification_status": r[7]} if r else next((s for s in sections if s["act"] == act), None))
        if best:
            # for a list of laws, what the Act is for matters most: lead with its official long title
            lt = long_title(about.get(act))
            out.append({**best, "text": f"[Long title of the Act] {lt}\n[Section {best['section']}] {best['text']}"}
                       if lt else best)
    return out


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

def rrf(*rankings: list[tuple[Any, float]], k: int = 60) -> list[tuple[Any, float]]:
    scores: dict[Any, float] = {}
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
