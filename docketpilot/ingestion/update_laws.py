"""Weekly law update: fetch every Act again from India Code and record what changed. No AI is used.

    python -m docketpilot.ingestion.update_laws            # all Acts (the weekly scheduled task runs this)
    python -m docketpilot.ingestion.update_laws --act "NI Act" --act BNSS

For each section, the new text's SHA-256 fingerprint is compared with the stored current version:
  * same fingerprint      -> nothing to do;
  * different             -> the stored version is kept as an earlier version (valid_to is set) and the new text
                             becomes the current version, with its amendment footnotes;
  * new section number    -> added;
  * section gone          -> the stored version is closed (valid_to = today), nothing is deleted.
Statute search reads PostgreSQL directly, so no search re-index is needed. Each Act is its own transaction, and
an Act whose download looks broken (far fewer sections than stored) is skipped, never half-applied.
The run, its changes and the drafts that cite a changed section go into the law_updates table (shown on the
dashboard). Everything stays 'unverified' (decision 11).
"""
import argparse
import json
import logging
import time
from collections import defaultdict
from datetime import date, datetime
from typing import Any

import psycopg

from docketpilot.ingestion.load import connect
from docketpilot.knowledge import statutes
from docketpilot.knowledge.statutes import ParsedSection

log = logging.getLogger("update_laws")
MIN_SHARE = 0.5  # a download with under half the stored sections is treated as a failed download


def _insert(cur: psycopg.Cursor, act_id: Any, sec: ParsedSection) -> None:
    cur.execute("""INSERT INTO section_versions (act_id, section_number, heading, text, inserted_on, valid_from,
                   valid_to, footnotes, source_url, content_sha256) VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s)""",
                (act_id, sec.number, sec.heading, sec.text, sec.inserted_on, sec.valid_from, sec.footnotes_raw,
                 sec.source_url, sec.sha256))
    cur.execute("DELETE FROM amendments WHERE act_id=%s AND section_number=%s", (act_id, sec.number))
    for f in sec.footnotes:
        cur.execute("INSERT INTO amendments (act_id, section_number, note, action, amending_act, effective_date) "
                    "VALUES (%s,%s,%s,%s,%s,%s)", (act_id, sec.number, f.note, f.action, f.amending_act, f.effective))


def compare(stored: dict[str, list[str]], fresh: dict[str, list[ParsedSection]]) -> dict[str, list[str]]:
    """Section numbers that were added, changed or removed (by text fingerprint; order of duplicates ignored)."""
    out: dict[str, list[str]] = {"added": [], "changed": [], "removed": []}
    for number in sorted(set(stored) | set(fresh)):
        old, new = sorted(stored.get(number, [])), sorted(s.sha256 for s in fresh.get(number, []))
        if old == new:
            continue
        out["added" if not old else "removed" if not new else "changed"].append(number)
    return out


def update_act(conn: psycopg.Connection, short: str, india_code_id: str, today: date) -> dict[str, Any]:
    items = statutes.fetch_act(india_code_id, refresh=True)
    fresh: dict[str, list[ParsedSection]] = defaultdict(list)
    for item in items:
        sec = statutes.parse_section(item)
        if sec is not None and sec.number:
            fresh[sec.number].append(sec)
    with conn.cursor() as cur:
        cur.execute("SELECT id, title FROM acts WHERE india_code_act_id=%s", (india_code_id,))
        row = cur.fetchone()
        if row is None:
            return {"act": short, "skipped": "not loaded yet (run ingestion.load --step statutes first)"}
        act_id, title = row
        cur.execute("SELECT section_number, content_sha256 FROM section_versions WHERE act_id=%s AND valid_to IS NULL",
                    (act_id,))
        stored: dict[str, list[str]] = defaultdict(list)
        for number, sha in cur.fetchall():
            stored[number].append(sha)
        if sum(map(len, fresh.values())) < MIN_SHARE * sum(map(len, stored.values())):
            raise RuntimeError(f"India Code returned {sum(map(len, fresh.values()))} sections, "
                               f"{sum(map(len, stored.values()))} are stored; download looks incomplete")
        diff = compare(stored, fresh)
        changes: list[dict[str, Any]] = []
        for kind in ("changed", "removed", "added"):
            for number in diff[kind]:
                new = fresh.get(number, [])
                if kind != "added":  # close the old version(s); the day the new wording started, or today
                    start = max((s.valid_from for s in new if s.valid_from), default=None)
                    cur.execute("SELECT max(valid_from) FROM section_versions WHERE act_id=%s AND section_number=%s "
                                "AND valid_to IS NULL", (act_id, number))
                    old_from = cur.fetchone()[0]  # type: ignore[index]
                    end = start if start and (old_from is None or start > old_from) else today
                    cur.execute("UPDATE section_versions SET valid_to=%s WHERE act_id=%s AND section_number=%s "
                                "AND valid_to IS NULL", (end, act_id, number))
                for sec in new:
                    _insert(cur, act_id, sec)
                heading = (new[0].heading if new else "")[:200]
                changes.append({"act": title, "short": short, "section": number, "kind": kind, "heading": heading,
                                "in_force_from": str(new[0].valid_from) if new and new[0].valid_from else None})
    conn.commit()
    return {"act": short, "sections": sum(map(len, fresh.values())), "changes": changes}


def affected_drafts(conn: psycopg.Connection, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drafts whose verification report cites a section that changed or was removed."""
    hits: dict[str, dict[str, Any]] = {}
    with conn.cursor() as cur:
        for c in changes:
            if c["kind"] == "added":
                continue
            cur.execute("""SELECT d.id::text, d.matter_id::text, d.status FROM drafts d,
                                  jsonb_array_elements(coalesce(d.verification->'statutes', '[]'::jsonb)) s
                           WHERE d.status <> 'failed' AND upper(s->>'section') = upper(%s)
                             AND (s->>'act' = %s OR s->>'act' = %s)""", (c["section"], c["act"], c["short"]))
            for draft_id, matter_id, status in cur.fetchall():
                h = hits.setdefault(draft_id, {"draft_id": draft_id, "matter_id": matter_id, "status": status, "sections": []})
                h["sections"].append(f"{c['short']} s.{c['section']}")
    return list(hits.values())


def run(only: list[str] | None = None) -> dict[str, Any]:
    started, today = datetime.now().astimezone(), date.today()
    acts = {k: v for k, v in statutes.ACTS.items() if not only or k in only}
    results, failed = [], []
    with connect() as conn:
        for short, (india_code_id, *_rest) in acts.items():
            try:
                r = update_act(conn, short, india_code_id, today)
                results.append(r)
                n = len(r.get("changes", []))
                log.info("%s: %s", short, f"{n} change(s)" if n else r.get("skipped", "no change"))
            except Exception as e:  # one Act failing (site down, format change) must not stop the others
                conn.rollback()
                failed.append({"act": short, "error": str(e)[:300]})
                log.warning("%s: FAILED %s", short, e)
        changes = [c for r in results for c in r.get("changes", [])]
        drafts = affected_drafts(conn, changes)
        summary = {"acts_checked": len(results), "added": sum(c["kind"] == "added" for c in changes),
                   "changed": sum(c["kind"] == "changed" for c in changes),
                   "removed": sum(c["kind"] == "removed" for c in changes)}
        conn.execute("""INSERT INTO law_updates (started_at, finished_at, acts_checked, sections_added, sections_changed,
                        sections_removed, changes, failed, affected_drafts) VALUES (%s, now(), %s,%s,%s,%s,%s,%s,%s)""",
                     (started, summary["acts_checked"], summary["added"], summary["changed"], summary["removed"],
                      json.dumps(changes), json.dumps(failed), json.dumps(drafts)))
        conn.commit()
    return {**summary, "failed": failed, "affected_drafts": len(drafts), "minutes": round((time.time() - started.timestamp()) / 60, 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--act", action="append", help="short name, e.g. 'NI Act' (repeatable); default: all Acts")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    print(json.dumps(run(args.act), indent=1))


if __name__ == "__main__":
    main()
