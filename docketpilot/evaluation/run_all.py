"""One command for the whole evaluation report (spec 17, Phase 8).

    python -m docketpilot.evaluation.run_all            # everything except the slow end-to-end run
    python -m docketpilot.evaluation.run_all --e2e      # also run the end-to-end flow (uses Groq quota)

Writes reports/EVALUATION_REPORT.md and reports/*.json. Every number in the report comes from this run
(or, for e2e, from reports/e2e.json, whose timestamp is shown).
"""
import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docketpilot.config import get_settings
from docketpilot.evaluation import fake_citations, pii, retrieval_latency
from docketpilot.ingestion.load import connect

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"


def versions(conn: Any) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("""SELECT count(*), count(*) FILTER (WHERE has_text), count(*) FILTER (WHERE is_s138),
                              count(*) FILTER (WHERE court_level='HC') FROM cases""")
        cases, with_text, s138, hc = cur.fetchone()
        cur.execute("SELECT count(*) FROM chunks")
        chunks = cur.fetchone()[0]
        cur.execute("SELECT count(*), count(cited_case_id) FROM citation_edges")
        edges, resolved = cur.fetchone()
        cur.execute("SELECT count(*) FROM case_citations WHERE origin = 'mined'")
        aliases = cur.fetchone()[0]
    prompts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:12] for p in sorted((ROOT / "prompts").glob("*.md"))}
    s = get_settings()
    return {"corpus": {"cases": cases, "with_full_text": with_text, "s138_cases": s138, "hc_cases": hc,
                       "chunks": chunks, "citation_edges": edges, "edges_resolved": resolved, "mined_aliases": aliases,
                       "sources": "AWS Open Data: indian-supreme-court-judgments (metadata 1950-2026, text 2020-2026 "
                                  "partial), indian-high-court-judgments (sample 2023-2024); India Code (NI Act)"},
            "models": {"llm": s.llm_primary_model + " (Groq)", "embedding": s.embed_model, "reranker": s.rerank_model},
            "prompts_sha256": prompts}


def md_table(rows: list[list[Any]], head: list[str]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] +
                     ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def write_report(r: dict[str, Any]) -> str:
    v, fc, pi, rt, st, lat, e2e = (r["versions"], r["fake_citations"], r["pii"], r["retrieval"], r["statutes"],
                                   r["latency"], r.get("e2e"))
    c = v["corpus"]
    lines = [
        "# DocketPilot — Evaluation Report (prototype)",
        f"Generated {r['generated_at']} by `python -m docketpilot.evaluation.run_all`. Re-run to reproduce.",
        "",
        "**Read this first.** Prototype corpus (~3 GB of open data), no lawyer review of any legal data, "
        "synthetic test data only. Numbers below are real measurements of this build; several miss the spec's "
        "targets and are reported as measured (spec 18.13).",
        "",
        "## 1. Corpus and versions",
        md_table([[k, f"{val:,}" if isinstance(val, int) else val] for k, val in c.items()], ["Item", "Value"]),
        "", md_table([[k, val] for k, val in v["models"].items()], ["Model role", "Model"]),
        "", "Prompt versions (sha256 prefix): " + ", ".join(f"`{k}` {h}" for k, h in v["prompts_sha256"].items()),
        "",
        "## 2. Citation verification — fake-citation benchmark (spec 16.2)",
        f"Seed {fc['seed']}; {fc['n_cases']} real SC cases; {fc['overall']['fakes']} fakes, {fc['overall']['reals']} real.",
        md_table([[t, d["n"], d.get("caught_rate", ""), d.get("false_alarm_rate", "")] for t, d in fc["per_type"].items()],
                 ["Type", "n", "Caught (fakes)", "False alarm (real)"]),
        "",
        f"**Overall:** recall {fc['overall']['recall']}, precision {fc['overall']['precision']}, F1 {fc['overall']['f1']}. "
        "Target recall >= 0.95.",
        "Limit: fakes are derived from the same corpus the verifier searches, so this tests the verifier's logic "
        "on known cases, not coverage of all Indian law. 'Wrong proposition' rows (if present) use the Groq judge "
        "on a small sample.",
        "",
        "## 3. Privacy — synthetic Indian PII (spec 10.1, 16.4)",
        md_table([[k, pi[k]["recall"], pi[k]["leakage_rate"], pi[k]["precision"]] for k in
                  ("with_ner", "rules_only", "heldout_with_ner")], ["Set", "Recall", "Leakage", "Precision"]),
        "",
        f"Target leakage < 1%. **Realistic figure: held-out leakage {pi['heldout_with_ner']['leakage_rate']:.1%}** "
        f"(per type: {pi['heldout_with_ner']['per_type_recall']}). The first two rows use templates the rules "
        "were tuned on and are optimistic. Missed items are mostly person names without cues; the lawyer preview "
        "step is the safeguard.",
        "",
        "## 4. Retrieval (spec 16.1)",
        f"Task: {rt['task']}; n = {rt['n_queries']} (indicative only; no lawyer-labelled gold set).",
        md_table([[m, rt[m]["recall@1"], rt[m]["recall@5"], rt[m]["mrr@10"], rt[m]["p50_ms"], rt[m]["p95_ms"]]
                  for m in ("lexical", "dense", "hybrid", "hybrid_rerank")],
                 ["Mode", "R@1", "R@5", "MRR@10", "p50 ms", "p95 ms"]),
        "", "Dense index covers Section 138 judgments only (CPU embedding speed); lexical covers all chunks.",
        "",
        "## 5. Statute date logic (spec 16.3)",
        f"{st['passed']}/{st['boundary_checks']} boundary checks passed across {st['sections']} NI Act sections. "
        + st["note"],
        "",
        "## 6. Latency (spec 15)",
        md_table([[k, d.get("p50_ms", ""), d.get("p95_ms", d.get("seconds", "")),
                   d.get("target_p95_ms", d.get("target_seconds", ""))] for k, d in lat.items()],
                 ["Operation", "p50 ms", "p95 ms / seconds", "Target"]),
        "", lat["verify_20_citation_draft_without_llm"]["note"],
        "",
        "## 7. End-to-end flow (Phase 6/7 acceptance)",
    ]
    if e2e:
        lines += [f"From `reports/e2e.json` (run {e2e.get('run_at')}). Draft generation took {e2e.get('draft_seconds')} s.",
                  md_table([[s["step"], json.dumps({k: v for k, v in s.items() if k not in ('step', 'facts', 'trace')},
                                                   default=str)[:150]] for s in e2e.get("steps", [])], ["Step", "Result"]),
                  "", f"Reminders created: {e2e.get('reminders')}", "",
                  f"Verification gate: {e2e.get('gate_check')}"]
    else:
        lines.append("Not run. Use `--e2e`.")
    lines += ["", "## 8. Known limits",
              "- Not legal advice. Nothing was reviewed by a lawyer or double-checked by the team (decision 11).",
              "- Corpus is a small open-data sample; 'not found' is common and does not mean a case is fake.",
              "- Most SCC/AIR citations are not resolvable (no open reporter metadata); aliases are mined heuristically.",
              "- Only current statute wording is stored; earlier versions are reported as not stored.",
              "- No OCR or voice input in this prototype; scanned PDFs are rejected with a message.",
              "- Single LLM (Groq free tier); when it is unavailable, AI steps pause and say so."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--e2e", action="store_true")
    ap.add_argument("--llm-n", type=int, default=6, help="wrong-proposition cases judged by the LLM")
    args = ap.parse_args()
    REPORTS.mkdir(exist_ok=True)
    if args.e2e:
        subprocess.run([sys.executable, "-m", "docketpilot.evaluation.e2e"], check=False)  # noqa: S603
    with connect() as conn:
        r: dict[str, Any] = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "versions": versions(conn)}
        print("fake citations...", flush=True)
        r["fake_citations"] = asyncio.run(fake_citations.main_async(150, args.llm_n, 13))
        print("pii...", flush=True)
        r["pii"] = {"with_ner": pii.evaluate(200, 7, True), "rules_only": pii.evaluate(200, 7, False),
                    "heldout_with_ner": pii.evaluate(200, 8, True, heldout=True)}
        print("retrieval...", flush=True)
        r["retrieval"] = retrieval_latency.retrieval_eval(conn)
        print("statutes + latency...", flush=True)
        r["statutes"] = retrieval_latency.statute_boundaries(conn)
        r["latency"] = retrieval_latency.latency(conn)
    e2e_file = REPORTS / "e2e.json"
    if e2e_file.exists():
        r["e2e"] = json.loads(e2e_file.read_text(encoding="utf-8"))
    for k in ("pii",):
        for v in r[k].values():
            v.pop("examples", None)
    (REPORTS / "evaluation.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (REPORTS / "EVALUATION_REPORT.md").write_text(write_report(r), encoding="utf-8")
    print(f"written {REPORTS / 'EVALUATION_REPORT.md'}")


if __name__ == "__main__":
    main()
