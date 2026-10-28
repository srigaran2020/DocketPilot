"""Load the knowledge base into PostgreSQL. Safe to re-run: already-loaded judgments are skipped.

    python -m docketpilot.ingestion.load            # everything
    python -m docketpilot.ingestion.load --step texts

Steps: sc_metadata (all SC cases 1950-2026 + their SCR/neutral citations), texts (downloaded SC/HC
judgments -> segments, chunks, citation edges), aliases (parallel citations mined from text),
resolve (link citation edges to cases), statutes (India Code).
"""
import argparse
import hashlib
import re
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import psycopg

from docketpilot.config import get_settings
from docketpilot.knowledge import citations as cit
from docketpilot.knowledge import parse, statutes

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
NS = uuid.UUID("6f1c2a54-2b8e-4d0e-9a51-6b1d3e4c5a10")  # fixed namespace -> stable case ids across re-runs
SC_LICENCE = HC_LICENCE = "CC-BY-4.0"


def connect() -> psycopg.Connection:
    url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg.connect(url)


def sc_id(path: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"sc:{path}")


def hc_id(cnr: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"hc:{cnr}")


def _date(s: object) -> date | None:
    if s is None or (isinstance(s, float) and pd.isna(s)) or s is pd.NaT:
        return None
    if isinstance(s, datetime | pd.Timestamp):
        return s.date()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s).strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def _s(x: object) -> str | None:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    t = str(x).strip()
    return t or None


# ---------------- SC metadata ----------------

def load_sc_metadata(conn: psycopg.Connection) -> None:
    cols = ["title", "petitioner", "respondent", "judge", "citation", "cnr", "decision_date",
            "disposal_nature", "path", "nc_display"]
    files = sorted((RAW / "sc_metadata" / "metadata" / "parquet").glob("year=*/metadata.parquet"))
    n_cases = n_cits = 0
    with conn.cursor() as cur:
        for f in files:
            year = int(re.search(r"year=(\d+)", str(f)).group(1))  # type: ignore[union-attr]
            df = pd.read_parquet(f, columns=cols)
            for r in df.itertuples(index=False):
                cid = sc_id(r.path)
                cur.execute("SELECT 1 FROM cases WHERE id=%s", (cid,))
                if cur.fetchone():
                    continue
                # Several reported judgments can share one CNR (same case, different decisions): keep them all,
                # storing the CNR only on the first.
                cnr = _s(r.cnr)
                if cnr:
                    cur.execute("SELECT 1 FROM cases WHERE cnr=%s", (cnr,))
                    if cur.fetchone():
                        cnr = None
                cur.execute(
                    """INSERT INTO cases (id, court, court_level, cnr, title, petitioner, respondent, decision_date,
                       year, judges, disposal_nature, outcome, outcome_confidence, source, source_key, licence)
                       VALUES (%s,'Supreme Court of India','SC',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (cid, cnr, _s(r.title) or "", _s(r.petitioner), _s(r.respondent), _date(r.decision_date),
                     year, _s(r.judge), _s(r.disposal_nature), *parse.outcome("", _s(r.disposal_nature)),
                     "AWS Open Data: indian-supreme-court-judgments", f"data/pdf/year={year}/english/{r.path}_EN.pdf",
                     SC_LICENCE),
                )
                n_cases += 1
                for raw in (_s(r.citation), _s(r.nc_display)):
                    c = cit.normalise(raw) if raw else None
                    if c and c.kind in ("scr", "neutral"):
                        cur.execute("INSERT INTO case_citations (case_id, kind, raw, canonical) VALUES (%s,%s,%s,%s)",
                                    (cid, c.kind, raw, c.canonical))
                        n_cits += 1
            conn.commit()
    print(f"sc_metadata: {n_cases} new cases, {n_cits} citations")


# ---------------- judgment texts ----------------

def _hc_metadata_index() -> dict[str, dict]:
    """file stem -> metadata row, for every HC bench/year we downloaded metadata for."""
    index: dict[str, dict] = {}
    root = RAW / "hc_metadata" / "metadata" / "parquet"
    for f in root.glob("year=*/court=*/bench=*/metadata.parquet"):
        m = re.search(r"year=(\d+).court=([^\\/]+).bench=([^\\/]+)", str(f))
        if not m:
            continue
        df = pd.read_parquet(f, columns=["title", "cnr", "decision_date", "judge", "pdf_link", "court"])
        for r in df.itertuples(index=False):
            stem = Path(str(r.pdf_link)).stem
            index[stem] = {"title": _s(r.title) or "", "cnr": _s(r.cnr), "date": _date(r.decision_date),
                           "judge": _s(r.judge), "court": _s(r.court), "year": int(m.group(1)),
                           "bench": m.group(3), "key": f"data/pdf/year={m.group(1)}/court={m.group(2)}/"
                           f"bench={m.group(3)}/{Path(str(r.pdf_link)).name}"}
    return index


def _split_title(title: str) -> tuple[str | None, str | None, str | None]:
    case_type = title.split("/", 1)[0].strip() if "/" in title else None
    m = re.search(r"\bof\s+(.*?)\s+Vs\.?\s+(.*)$", title, re.I)
    return case_type, (m.group(1).strip() if m else None), (m.group(2).strip() if m else None)


def _store_text(cur: psycopg.Cursor, case_id: uuid.UUID, raw: str, is_scr: bool, disposal: str | None) -> int:
    text = parse.clean(raw)
    segs = parse.split_headnote(text, is_scr)
    body = " ".join(s.text for s in segs if s.role == "body")
    label, conf = parse.outcome(body, disposal)
    raw = raw.replace("\x00", "")
    cur.execute("UPDATE cases SET has_text=true, is_s138=%s, outcome=%s, outcome_confidence=%s, content_sha256=%s "
                "WHERE id=%s", (parse.is_s138(text), label, conf, hashlib.sha256(raw.encode()).hexdigest(), case_id))
    seg_ids = {}
    for i, s in enumerate(segs):
        cur.execute("INSERT INTO segments (case_id, role, ord, char_start, char_end, text) VALUES (%s,%s,%s,%s,%s,%s) "
                    "RETURNING id", (case_id, s.role, i, s.start, s.end, s.text))
        seg_ids[s.start] = cur.fetchone()[0]  # type: ignore[index]
    chunks = parse.chunk(text, segs)
    rows = []
    for i, ch in enumerate(chunks):
        seg_start = max(s.start for s in segs if s.start <= ch.start)
        rows.append((case_id, seg_ids[seg_start], ch.role, i, ch.page, ch.start, ch.end, ch.text))
    cur.executemany("INSERT INTO chunks (case_id, segment_id, role, ord, page, char_start, char_end, text) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    # A High Court neutral citation in the header (first ~2000 chars) is the judgment's own citation.
    own = None
    if not is_scr:
        own = next((c for c in cit.find_citations(text[:2000]) if c.kind == "hc_neutral"), None)
        if own:
            cur.execute("INSERT INTO case_citations (case_id, kind, raw, canonical) VALUES (%s,%s,%s,%s)",
                        (case_id, own.kind, own.raw, own.canonical))
    # Citation graph edges come from the judgment body only (headnotes are editorial).
    edges = []
    for s in segs:
        if s.role != "body":
            continue
        for c in cit.find_citations(s.text):
            if own and c.canonical == own.canonical:
                continue
            sentence = cit.sentence_around(s.text, c.start, c.end)
            edges.append((case_id, c.kind, c.raw, c.canonical, cit.signal_for(sentence), sentence, s.start + c.start))
    cur.executemany("INSERT INTO citation_edges (citing_case_id, kind, raw, canonical, signal, sentence, char_start) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)", edges)
    return len(chunks)


def load_texts(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM cases WHERE has_text")
        done = {r[0] for r in cur.fetchall()}
    n_docs = n_chunks = skipped = 0

    for txt in sorted((RAW / "sc_pdf").glob("*/*_EN.txt")):
        path = txt.name[: -len("_EN.txt")]
        cid = sc_id(path)
        if cid in done:
            continue
        with conn.cursor() as cur:
            cur.execute("SELECT disposal_nature FROM cases WHERE id=%s", (cid,))
            row = cur.fetchone()
            if row is None:
                skipped += 1
                continue
            n_chunks += _store_text(cur, cid, txt.read_text(encoding="utf-8"), True, row[0])
        conn.commit()
        n_docs += 1
        if n_docs % 200 == 0:
            print(f"  texts: {n_docs} docs, {n_chunks} chunks", flush=True)

    hc_index = _hc_metadata_index()
    for txt in sorted((RAW / "hc_pdf").glob("*/*/*.txt")):
        meta = hc_index.get(txt.stem)
        if not meta or not meta["cnr"]:
            skipped += 1
            continue
        cid = hc_id(meta["cnr"])
        if cid in done:
            continue
        case_type, pet, resp = _split_title(meta["title"])
        court = meta["court"] or meta["bench"]
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO cases (id, court, court_level, bench, cnr, case_type, title, petitioner, respondent,
                   decision_date, year, judges, source, source_key, licence)
                   VALUES (%s,%s,'HC',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (cid, court, meta["bench"], meta["cnr"], case_type, meta["title"], pet, resp, meta["date"],
                 meta["year"], meta["judge"], "AWS Open Data: indian-high-court-judgments", meta["key"], HC_LICENCE),
            )
            if cur.rowcount == 0:
                conn.rollback()
                continue
            n_chunks += _store_text(cur, cid, txt.read_text(encoding="utf-8"), False, None)
        conn.commit()
        n_docs += 1
        if n_docs % 200 == 0:
            print(f"  texts: {n_docs} docs, {n_chunks} chunks", flush=True)
    print(f"texts: {n_docs} new judgments, {n_chunks} chunks, {skipped} skipped (no metadata)")


# ---------------- aliases and resolution ----------------

_PARALLEL_GAP = re.compile(r"^\s*[:;,=]?\s*(?:and\s+)?$", re.I)


def mine_aliases(conn: psycopg.Connection) -> None:
    """Parallel citations ('(2014) 9 SCC 129 : 2014 INSC 520') link a reporter citation to a known case.
    The mined alias gets confidence 0.9 (spec 5.4)."""
    added = 0
    with conn.cursor() as cur:
        cur.execute("SELECT citing_case_id, kind, canonical, raw, char_start FROM citation_edges "
                    "ORDER BY citing_case_id, char_start")
        rows = cur.fetchall()
        cur.execute("SELECT kind, canonical, case_id FROM case_citations")
        known = {(k, c): cid for k, c, cid in cur.fetchall()}
        seen: set[tuple[str, str]] = set(known)
        for a, b in zip(rows, rows[1:], strict=False):
            if a[0] != b[0] or b[4] - (a[4] + len(a[3])) > 6:
                continue
            for x, y in ((a, b), (b, a)):
                target = known.get((x[1], x[2]))
                if target and (y[1], y[2]) not in seen and y[1] not in ("scr", "neutral"):
                    cur.execute("INSERT INTO case_citations (case_id, kind, raw, canonical, confidence, origin) "
                                "VALUES (%s,%s,%s,%s,0.9,'mined')", (target, y[1], y[3], y[2]))
                    seen.add((y[1], y[2]))
                    added += 1
    conn.commit()
    print(f"aliases: {added} mined")


def hc_own_citations(conn: psycopg.Connection) -> None:
    """One-off fix for HC judgments loaded before own-citation detection: move a header neutral citation
    from citation_edges to case_citations."""
    with conn.cursor() as cur:
        cur.execute("""
            WITH own AS (
                SELECT DISTINCT ON (e.citing_case_id) e.id, e.citing_case_id, e.raw, e.canonical
                FROM citation_edges e JOIN cases c ON c.id = e.citing_case_id
                WHERE c.court_level = 'HC' AND e.kind = 'hc_neutral' AND e.char_start < 2000
                  AND NOT EXISTS (SELECT 1 FROM case_citations cc
                                  WHERE cc.case_id = e.citing_case_id AND cc.kind = 'hc_neutral')
                ORDER BY e.citing_case_id, e.char_start)
            , ins AS (INSERT INTO case_citations (case_id, kind, raw, canonical)
                      SELECT citing_case_id, 'hc_neutral', raw, canonical FROM own RETURNING case_id, canonical)
            DELETE FROM citation_edges e USING ins
            WHERE e.citing_case_id = ins.case_id AND e.kind = 'hc_neutral' AND e.canonical = ins.canonical""")
        print(f"hc_own_citations: {cur.rowcount} self-citation edges moved")
    conn.commit()


def resolve_edges(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("""UPDATE citation_edges e SET cited_case_id = c.case_id FROM case_citations c
                       WHERE e.cited_case_id IS NULL AND c.kind = e.kind AND c.canonical = e.canonical""")
        n = cur.rowcount
        cur.execute("SELECT count(*), count(cited_case_id) FROM citation_edges")
        total, resolved = cur.fetchone()  # type: ignore[misc]
    conn.commit()
    print(f"resolve: {n} newly linked; {resolved}/{total} edges resolved overall")


# ---------------- statutes ----------------

def load_statutes(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        for short, (act_id, title, number, year) in statutes.ACTS.items():
            cur.execute("""INSERT INTO acts (india_code_act_id, short_name, title, act_number, year)
                           VALUES (%s,%s,%s,%s,%s) ON CONFLICT (india_code_act_id) DO UPDATE SET title=EXCLUDED.title
                           RETURNING id""", (act_id, short, title, number, year))
            aid = cur.fetchone()[0]  # type: ignore[index]
            cur.execute("DELETE FROM section_versions WHERE act_id=%s", (aid,))
            cur.execute("DELETE FROM amendments WHERE act_id=%s", (aid,))
            n = 0
            for item in statutes.fetch_act(act_id):
                sec = statutes.parse_section(item)
                if sec is None:
                    continue
                cur.execute("""INSERT INTO section_versions (act_id, section_number, heading, text, inserted_on,
                               valid_from, valid_to, footnotes, source_url, content_sha256)
                               VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s)""",
                            (aid, sec.number, sec.heading, sec.text, sec.inserted_on, sec.valid_from,
                             sec.footnotes_raw, sec.source_url, sec.sha256))
                for f in sec.footnotes:
                    cur.execute("INSERT INTO amendments (act_id, section_number, note, action, amending_act, "
                                "effective_date) VALUES (%s,%s,%s,%s,%s,%s)",
                                (aid, sec.number, f.note, f.action, f.amending_act, f.effective))
                n += 1
            print(f"statutes: {short}: {n} sections")
    conn.commit()


STEPS = {"sc_metadata": load_sc_metadata, "texts": load_texts, "hc_own": hc_own_citations,
         "aliases": mine_aliases, "resolve": resolve_edges, "statutes": load_statutes}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=list(STEPS), action="append")
    args = ap.parse_args()
    with connect() as conn:
        for name in args.step or list(STEPS):
            STEPS[name](conn)


if __name__ == "__main__":
    main()
