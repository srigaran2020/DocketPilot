"""Ablation of the anti-hallucination pipeline: add one DocketPilot layer at a time and measure unreliable citations.

Same 8 questions and the same model (gpt-oss-120b on Groq) in every arm:
  A  LLM alone          closed book, asked to cite Indian judgments (answers saved by benchmark_vs.py)
  B  + retrieval        DocketPilot's sources in the prompt, model cites freely by name and citation
  C  + source tags      DocketPilot's prompt: legal statements must carry [P1]/[S1] tags, swapped for real citations
  D  + verification     C, then the verifier and auto-correction (the full DocketPilot answer)

Every arm's text goes through the same checks: existence (does the citation match a real Supreme Court judgment in the
store; formats the store does not fully cover are excluded) and support (AI judge: does the cited passage support the
sentence; quote check). The full-pipeline run also records per-stage seconds and tokens.

    python -m docketpilot.evaluation.ablation [--n 8]        -> reports/ablation.json
"""
import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docketpilot import chat
from docketpilot.evaluation.benchmark_vs import COVERED, QUESTIONS, Counting, _retry, cost
from docketpilot.ingestion.load import connect
from docketpilot.knowledge.citations import find_citations
from docketpilot.llm import get_llm
from docketpilot.verification.correct import BAD_PROPOSITION, BAD_QUOTE
from docketpilot.verification.engine import verify

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "ablation.json"

FREE_CITE = ("You are a legal research assistant for Indian advocates. Answer the question using the SOURCES below and "
             "support each legal point with citations to Indian judgments (case name and citation).")


def score(report: dict[str, Any]) -> dict[str, int]:
    """Per-citation outcome. fabricated: SC neutral/SCR citation matching no judgment, or citing a different case.
    unsupported: a real case whose passage does not support the sentence, or whose quote is not in it."""
    out = {"citations": 0, "fabricated": 0, "unsupported": 0, "outside_coverage": 0}
    for c in report.get("citations", []):
        out["citations"] += 1
        if c["verdict"] not in ("VERIFIED", "PARTIAL"):
            kinds = {x.kind for x in find_citations(c["raw"])}
            out["fabricated" if (kinds & COVERED or c["verdict"] == "CONFLICT") else "outside_coverage"] += 1
        elif (c.get("proposition") or {}).get("label") in BAD_PROPOSITION or any(q["status"] in BAD_QUOTE for q in c.get("quotes", [])):
            out["unsupported"] += 1
    return out


async def run(n: int) -> dict[str, Any]:
    llm = get_llm()
    prior = json.loads((ROOT / "reports" / "benchmark_vs.json").read_text(encoding="utf-8"))["answers"]
    rows = []
    with connect() as conn:
        for i, q in enumerate(QUESTIONS[:n]):
            row: dict[str, Any] = {"question": q}
            counting, trace = Counting(llm), dict[str, Any]()
            t = time.perf_counter()
            out = await _retry(chat.answer, conn, counting, [{"role": "user", "content": q}], trace=trace)
            calls = counting.calls
            row["timing_s"] = {**trace["seconds"], "total": time.perf_counter() - t}
            row["tokens"] = {"answer_in": calls[0].input_tokens, "answer_out": calls[0].output_tokens,
                             "judge_in": sum(c.input_tokens for c in calls[1:]), "judge_out": sum(c.output_tokens for c in calls[1:]),
                             "judge_calls": len(calls) - 1}
            row["usd"] = cost(row["tokens"]["answer_in"] + row["tokens"]["judge_in"], row["tokens"]["answer_out"] + row["tokens"]["judge_out"])
            row["corrections"] = [c["action"] for c in out["corrections"]]
            # C and D: before and after verification, same checks
            row["C"] = score(await _retry(verify, conn, trace["before_verification"], llm))
            row["D"] = score(await _retry(verify, conn, out["answer"], llm))
            # B: same sources, free citing
            r = await _retry(llm.complete, [{"role": "system", "content": FREE_CITE},
                                            {"role": "user", "content": f"{trace['context']}\n\nQUESTION:\n{trace['question']}"}],
                             reasoning_effort="medium", max_tokens=4000)
            row["B"] = score(await _retry(verify, conn, r.text, llm))
            # A: LLM alone (answer saved by benchmark_vs.py for the same question)
            a_text = (prior[i].get("baseline_closed_book") or {}).get("answer") if i < len(prior) else None
            row["A"] = score(await _retry(verify, conn, a_text, llm)) if a_text else None
            print(json.dumps({k: row[k] for k in ("A", "B", "C", "D")}), flush=True)
            rows.append(row)
    agg = {}
    for arm in "ABCD":
        rs = [r[arm] for r in rows if r.get(arm)]
        tot = {k: sum(x[k] for x in rs) for k in ("citations", "fabricated", "unsupported", "outside_coverage")}
        checkable = tot["citations"] - tot["outside_coverage"]
        tot["fabricated_pct"] = 100 * tot["fabricated"] / checkable if checkable else 0.0
        tot["unsupported_pct"] = 100 * tot["unsupported"] / checkable if checkable else 0.0
        agg[arm] = tot
    stages = ["masking", "retrieval", "llm_answer", "verification", "auto_correction"]
    timing = {s: sum(r["timing_s"][s] for r in rows) / len(rows) for s in stages}
    tok = {k: sum(r["tokens"][k] for r in rows) / len(rows) for k in rows[0]["tokens"]}
    actions = [a for r in rows for a in r["corrections"]]
    funnel = {"citations_before": sum(r["C"]["citations"] for r in rows), "replaced": actions.count("replace"),
              "removed": actions.count("remove"), "kept_in_final": sum(r["D"]["citations"] for r in rows)}
    return {"generated": datetime.now(UTC).isoformat(), "model": "openai/gpt-oss-120b (Groq)", "n_questions": len(rows),
            "arms": agg, "timing_mean_s": timing, "tokens_mean": tok, "funnel": funnel, "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    res = asyncio.run(run(ap.parse_args().n))
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("arms", "timing_mean_s", "tokens_mean", "funnel")}, indent=1))


if __name__ == "__main__":
    main()
