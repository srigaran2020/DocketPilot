"""Retrieval quality, statute boundary checks and latency (spec 15, 16.1, 16.3).

Retrieval gold set (honest limit): no lawyer-labelled queries exist. We use a known-item task: the SCR
editorial headnote of a Section 138 Supreme Court judgment is the query; the target is that judgment's
body text (headnotes are excluded from search). Small n; treat as indicative only.
"""
import random
import time
from datetime import date, timedelta
from typing import Any

import psycopg

from docketpilot.retrieval import search as rs
from docketpilot.verification.engine import verify


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 1) if xs else 0.0


def retrieval_eval(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("""SELECT c.id::text, left(regexp_replace(s.text, '\\s+', ' ', 'g'), 600) FROM cases c
                       JOIN segments s ON s.case_id = c.id AND s.role = 'headnote'
                       WHERE c.is_s138 AND c.court_level = 'SC' AND length(s.text) > 300""")
        items = cur.fetchall()
    modes = ["lexical", "dense", "hybrid", "hybrid_rerank"]
    out: dict[str, Any] = {"n_queries": len(items), "task": "SCR headnote -> same judgment's body (s.138 SC cases)"}
    for mode in modes:
        ranks, lat = [], []
        for case_id, query in items:
            t = time.perf_counter()
            res = rs.search(conn, query[:500], rs.Filters(s138_only=True), mode=mode, k=10, pool=50)
            lat.append((time.perf_counter() - t) * 1000)
            cases = []
            for h in res["hits"]:
                if h["case_id"] not in cases:
                    cases.append(h["case_id"])
            ranks.append(cases.index(case_id) + 1 if case_id in cases else None)
        found = [r for r in ranks if r]
        out[mode] = {"recall@1": round(sum(1 for r in found if r <= 1) / len(ranks), 3) if ranks else 0,
                     "recall@5": round(sum(1 for r in found if r <= 5) / len(ranks), 3) if ranks else 0,
                     "mrr@10": round(sum(1 / r for r in found) / len(ranks), 3) if ranks else 0,
                     "p50_ms": _pct(lat, 50), "p95_ms": _pct(lat, 95)}
    return out


def statute_boundaries(conn: psycopg.Connection) -> dict[str, Any]:
    """For every amendment date in the ledger, the lookup must change status exactly at that date."""
    with conn.cursor() as cur:
        cur.execute("SELECT section_number, inserted_on, valid_from FROM section_versions sv "
                    "JOIN acts a ON a.id = sv.act_id WHERE a.short_name = 'NI Act'")
        rows = cur.fetchall()
    checks = passed = 0
    failures = []
    for sec, ins, vf in rows:
        for boundary, before_status in ((ins, "not_yet_in_force"), (vf, None)):
            if boundary is None:
                continue
            before = rs.statute_as_on(conn, "NI Act", sec, boundary - timedelta(days=1))["status"]
            on = rs.statute_as_on(conn, "NI Act", sec, boundary)["status"]
            ok = (before == before_status if before_status else before != "in_force") and \
                 (on in ("in_force", "earlier_version_not_stored") if boundary == ins else on == "in_force")
            checks += 1
            passed += ok
            if not ok:
                failures.append({"section": sec, "boundary": boundary.isoformat(), "before": before, "on": on})
    return {"sections": len(rows), "boundary_checks": checks, "passed": passed, "failures": failures[:10],
            "note": "Checks the lookup logic against the ledger parsed from India Code footnotes. Older wordings "
                    "are not stored, so 'as on' dates before the latest amendment return 'earlier_version_not_stored'."}


def latency(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT raw FROM case_citations WHERE kind IN ('scr','neutral') ORDER BY md5(id::text) LIMIT 200")
        cits = [r[0] for r in cur.fetchall()]
        cur.execute("""SELECT c.petitioner, c.respondent, cc.raw FROM cases c JOIN case_citations cc
                       ON cc.case_id = c.id AND cc.kind = 'scr' WHERE c.petitioner IS NOT NULL
                       ORDER BY md5(c.id::text) LIMIT 20""")
        draft_cits = cur.fetchall()
    t1 = []
    for c in cits:
        t = time.perf_counter()
        rs.lookup_citation(conn, c)
        t1.append((time.perf_counter() - t) * 1000)
    t2 = []
    rng = random.Random(3)
    for _ in range(100):
        d = date(rng.randint(1985, 2026), rng.randint(1, 12), rng.randint(1, 28))
        t = time.perf_counter()
        rs.statute_as_on(conn, "NI Act", rng.choice(["138", "139", "142", "143A", "148"]), d)
        t2.append((time.perf_counter() - t) * 1000)
    t3 = []
    for q in ["dishonour of cheque insufficient funds", "legally enforceable debt", "notice within thirty days",
              "compounding of offence", "interim compensation 143A", "vicarious liability director company",
              "presumption section 139 rebuttal", "territorial jurisdiction complaint", "limitation one month",
              "security cheque"] * 3:
        t = time.perf_counter()
        rs.search(conn, q, rs.Filters(), mode="lexical", k=10)
        t3.append((time.perf_counter() - t) * 1000)
    draft = " ".join(f"As held in {p.title()} v. {r.title()}, {raw}, the law is settled." for p, r, raw in draft_cits)
    import asyncio

    t = time.perf_counter()
    rep = asyncio.run(verify(conn, draft, llm=None))
    v_ms = (time.perf_counter() - t) * 1000
    return {
        "exact_citation_lookup": {"n": len(t1), "p50_ms": _pct(t1, 50), "p95_ms": _pct(t1, 95), "target_p95_ms": 50},
        "statute_as_on": {"n": len(t2), "p50_ms": _pct(t2, 50), "p95_ms": _pct(t2, 95), "target_p95_ms": 50},
        "lexical_search_all_courts": {"n": len(t3), "p50_ms": _pct(t3, 50), "p95_ms": _pct(t3, 95), "target_p95_ms": 150},
        "verify_20_citation_draft_without_llm": {"citations": len(rep["citations"]), "seconds": round(v_ms / 1000, 2),
                                                 "target_seconds": 20,
                                                 "note": "Step 6 (AI judge) adds roughly 2-6 s per citation with text."},
    }
