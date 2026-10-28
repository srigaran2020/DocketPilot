"""Fake-citation benchmark (spec 16.2).

Real citations come from the corpus metadata; fakes are made by controlled changes, one type at a time.
A fake counts as *caught* when the verifier does not mark it VERIFIED/green. A real citation counts as a
*false alarm* when it is not VERIFIED.

Honest limits: fakes are derived from the same corpus the verifier searches, so this measures the
verifier's logic on known cases, not coverage of all Indian law.

    python -m docketpilot.evaluation.fake_citations [--n 150] [--llm-n 12]
"""
import argparse
import asyncio
import json
import random
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from docketpilot.ingestion.load import connect
from docketpilot.llm import get_llm
from docketpilot.verification.engine import verify

REPORTS = Path(__file__).resolve().parents[2] / "reports"
FAKE_FIRST = ["Ramesh", "Kavitha", "Arjun", "Meena", "Suresh", "Lakshmi", "Vikram", "Anitha"]
FAKE_LAST = ["Traders", "Enterprises", "Finance Ltd.", "Agencies", "Exports", "Textiles"]


def _party(s: str | None) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = re.sub(r"\b(AND (ANOTHER|OTHERS|ORS\.?|ANR\.?)|& ORS\.?|& ANR\.?|ETC\.?)\b.*$", "", s, flags=re.I).strip(" ,.&")
    return s.title()[:60]


def sample_cases(conn: psycopg.Connection, n: int, seed: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT c.id, c.petitioner, c.respondent, c.year, cc.raw, cc.canonical, c.has_text
                       FROM cases c JOIN case_citations cc ON cc.case_id = c.id AND cc.kind = 'scr'
                       WHERE c.court_level = 'SC' AND c.petitioner IS NOT NULL AND c.respondent IS NOT NULL
                         AND length(c.petitioner) BETWEEN 4 AND 60 AND length(c.respondent) BETWEEN 4 AND 60
                       ORDER BY md5(c.id::text || %s) LIMIT %s""", (str(seed), n * 2))
        rows = cur.fetchall()
    return [{"id": str(r[0]), "pet": _party(r[1]), "resp": _party(r[2]), "year": r[3], "raw": r[4], "canon": r[5],
             "has_text": r[6]} for r in rows if _party(r[1]) and _party(r[2])][:n]


def _scr(year: int, vol_page: str) -> str:
    return f"[{year}] {vol_page}"


def make_items(cases: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    items = []
    for i, c in enumerate(cases):
        m = re.match(r"\[(\d{4})\]\s*(.*?)(\d+)\s*$", c["raw"])
        if not m:
            continue
        year, middle, page = int(m.group(1)), m.group(2), int(m.group(3))
        name = f"{c['pet']} v. {c['resp']}"
        items.append({"type": "real", "text": f"{name}, {c['raw']}"})
        items.append({"type": "wrong_page", "text": f"{name}, [{year}] {middle}{page + rng.randint(3, 40)}"})
        items.append({"type": "wrong_year", "text": f"{name}, [{year + rng.choice([-3, -2, 2, 3])}] {middle}{page}"})
        other = cases[(i + 7) % len(cases)]
        items.append({"type": "swapped_names", "text": f"{other['pet']} v. {other['resp']}, {c['raw']}"})
        items.append({"type": "wrong_court", "text": f"{name}, {year}:KER:{rng.randint(100, 99999)}"})
        fake_name = f"{rng.choice(FAKE_FIRST)} {rng.choice(FAKE_LAST)} v. {rng.choice(FAKE_FIRST)} {rng.choice(FAKE_LAST)}"
        items.append({"type": "invented", "text": f"{fake_name}, ({rng.randint(1990, 2024)}) {rng.randint(1, 12)} SCC "
                                                  f"{rng.randint(1, 900)}"})
    return items


async def run_existence(conn: psycopg.Connection, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        rep = await verify(conn, f"As held in {it['text']}, the law is settled.", llm=None)
        cits = rep["citations"]
        v = cits[0]["verdict"] if cits else "NOT_EXTRACTED"
        out.append({**it, "verdict": v, "flagged": v != "VERIFIED"})
    return out


async def run_propositions(conn: psycopg.Connection, n: int, seed: int) -> list[dict[str, Any]]:
    """Real case + a proposition taken from a *different* s.138 judgment (should not be supported),
    and real case + a sentence from its own body (should be supported)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT c.id, c.petitioner, c.respondent, cc.raw FROM cases c
                       JOIN case_citations cc ON cc.case_id = c.id AND cc.kind = 'scr'
                       WHERE c.has_text AND c.court_level = 'SC' ORDER BY md5(c.id::text || %s) LIMIT %s""",
                    (str(seed), n * 2))
        cases = cur.fetchall()
    llm = get_llm()
    out = []
    for i, (cid, pet, resp, raw) in enumerate(cases[:n * 2]):
        with conn.cursor() as cur:
            src = cid if i % 2 == 0 else cases[(i + 3) % len(cases)][0]
            cur.execute("""SELECT text FROM chunks WHERE case_id = %s AND role = 'body' AND length(text) > 600
                           ORDER BY md5(id::text) LIMIT 1""", (src,))
            row = cur.fetchone()
        if not row:
            continue
        sentences = [s.strip() for s in re.split(r"(?<=[.])\s+", row[0]) if 80 < len(s.strip()) < 300]
        if not sentences:
            continue
        prop = sentences[0].replace('"', "'")
        kind = "proposition_real" if src == cid else "wrong_proposition"
        draft = f"In {_party(pet)} v. {_party(resp)}, {raw}, the Court observed that {prop}"
        rep = await verify(conn, draft, llm=llm)
        p = (rep["citations"][0].get("proposition") or {}) if rep["citations"] else {}
        label = p.get("label", "none")
        flagged = label in ("does_not_support", "contradicts", "unsupported")
        out.append({"type": kind, "text": draft[:200], "verdict": label, "flagged": flagged})
        await asyncio.sleep(2)  # stay well inside Groq free-tier limits
    return out


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        by[r["type"]].append(r["flagged"])
    table = {}
    for t, flags in by.items():
        rate = sum(flags) / len(flags)
        key = "false_alarm_rate" if t in ("real", "proposition_real") else "caught_rate"
        table[t] = {"n": len(flags), key: round(rate, 3)}
    fakes = [r for r in rows if r["type"] not in ("real", "proposition_real")]
    reals = [r for r in rows if r["type"] in ("real", "proposition_real")]
    tp = sum(r["flagged"] for r in fakes)
    fp = sum(r["flagged"] for r in reals)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / len(fakes) if fakes else 0.0
    return {"per_type": table, "overall": {"fakes": len(fakes), "reals": len(reals), "recall": round(recall, 3),
                                           "precision": round(precision, 3),
                                           "f1": round(2 * precision * recall / (precision + recall), 3)
                                           if precision + recall else 0.0}}


async def main_async(n: int, llm_n: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    with connect() as conn:
        items = make_items(sample_cases(conn, n, seed), rng)
        rows = await run_existence(conn, items)
        if llm_n:
            rows += await run_propositions(conn, llm_n, seed)
    result = {"benchmark": "fake_citations_v1", "run_at": datetime.now(UTC).isoformat(), "seed": seed,
              "n_cases": n, "llm_cases": llm_n, **summarise(rows),
              "verdict_counts": {t: dict(sorted({r["verdict"]: sum(1 for x in rows if x["type"] == t and
                                                                     x["verdict"] == r["verdict"])
                                                  for r in rows if r["type"] == t}.items()))
                                 for t in sorted({r["type"] for r in rows})},
              "examples": rows[:14]}
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--llm-n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    result = asyncio.run(main_async(args.n, args.llm_n, args.seed))
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "fake_citations.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("per_type", "overall", "verdict_counts")}, indent=1))


if __name__ == "__main__":
    main()
