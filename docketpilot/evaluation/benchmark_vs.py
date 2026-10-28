"""Head-to-head measurements for the comparison with LegalMind (IEEE Access 2025) and other legal AI systems.

Three experiments, each DocketPilot vs a baseline that uses the SAME model (gpt-oss-120b on Groq), so the
difference comes from the system design, not from a different model:

1. Cost per research answer. DocketPilot: retrieval of reranked passages + statute sections, answer, then the
   verifier's AI-judge calls; every token is counted from real API responses. Baseline ("long-context LLM"):
   the same model given the full text of the same judgments and the same statute sections, the way a plain LLM
   reads whole cases. Its input is counted with the o200k tokenizer and priced; its output is assumed equal to
   DocketPilot's answer (which favours the baseline).
2. Document processing time. Real High Court judgments (public data) as "case papers": find the case number,
   parties and every dated event. DocketPilot: local case-number reader + masking + one structured, low-effort
   model call. Baseline: the same model reads the whole unmasked text with a generic prompt at default effort.
   Wall-clock time and correctness of the case number (against the court's own metadata) are measured.
3. Citation hallucination. The same questions answered by the plain model from memory ("cite Indian judgments")
   and by DocketPilot. Every citation in both outputs goes through the same existence check (no AI judge):
   a citation that matches no real judgment in the 41k-case store is counted as unverifiable.

    python -m docketpilot.evaluation.benchmark_vs [--n-questions 12] [--n-docs 10]
Writes reports/benchmark_vs.json.
"""
import argparse
import asyncio
import json
import random
import re
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docketpilot import casefile, chat
from docketpilot.ingestion.load import connect
from docketpilot.llm import LLMError, LLMResult, LLMUnavailable, get_llm
from docketpilot.privacy import redact as pii
from docketpilot.retrieval import search as rs
from docketpilot.verification.engine import verify

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "benchmark_vs.json"
PRICE_IN, PRICE_OUT = 0.15 / 1e6, 0.60 / 1e6  # USD per token, Groq list price for gpt-oss-120b (Oct 2026)

QUESTIONS = [  # every major practice area, not only cheque bounce
    "Is the presumption under Section 139 of the NI Act rebuttable, and what standard of proof does the accused need?",
    "What must a wife prove to get divorce on the ground of cruelty under the Hindu Marriage Act?",
    "When can a court grant anticipatory bail and what conditions can it impose?",
    "Can the High Court quash an FIR when the parties have settled a matrimonial dispute?",
    "When is specific performance of an agreement to sell immovable property refused?",
    "What is the limitation period to file a suit for recovery of money lent, and when does it start?",
    "When can an arbitral award be set aside under Section 34 of the Arbitration and Conciliation Act?",
    "Who can claim maintenance under Section 144 of the BNSS and what must be shown?",
    "When is a consumer complaint for deficiency in service by a builder maintainable?",
    "How is compensation calculated for death in a motor accident claim?",
    "Can a daughter claim a share in coparcenary property under the Hindu Succession Act?",
    "When is a dying declaration enough to convict without corroboration?",
    "What are the grounds for rejecting a plaint under Order VII Rule 11 CPC?",
    "When does delay in lodging an FIR become fatal to the prosecution case?",
    "Can a tenant be evicted for bona fide personal need of the landlord?",
    "What is the test for granting a temporary injunction?",
]


class Counting:
    """Wraps the LLM and adds up the tokens of every call (answer + verifier judge calls)."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.name, self.model = inner, inner.name, inner.model
        self.calls: list[LLMResult] = []

    async def complete(self, *a: Any, **k: Any) -> LLMResult:
        r = await self.inner.complete(*a, **k)
        self.calls.append(r)
        return r

    def tokens(self) -> tuple[int, int]:
        return sum(c.input_tokens for c in self.calls), sum(c.output_tokens for c in self.calls)


def _enc() -> Any:
    import tiktoken

    return tiktoken.get_encoding("o200k_base")


def cost(tin: int, tout: int) -> float:
    return tin * PRICE_IN + tout * PRICE_OUT


# Groq's free tier allows 8,000 tokens a minute. Each measured run starts with a fresh minute, so the clock measures
# processing, not queueing behind the other arm. A run that still hits the limit is retried and its time discarded.
PACE_S = 62


def _backoff(e: Exception) -> float:
    """Free tier also caps tokens per day (200k, rolling). When that is hit, sleep until Groq says capacity is back."""
    ra = getattr(e, "retry_after_s", None)
    return min(float(ra) + 5, 1800.0) if ra and ra > PACE_S else PACE_S


async def _retry(fn: Any, *a: Any, **k: Any) -> Any:
    for i in range(12):
        try:
            return await fn(*a, **k)
        except (LLMError, LLMUnavailable) as e:
            if i == 11:
                raise
            print(f"  waiting {_backoff(e):.0f}s: {e}", flush=True)
            await asyncio.sleep(_backoff(e))
    return None


async def _timed(fn: Any, *a: Any, **k: Any) -> tuple[Any, float]:
    """Wait for a fresh rate-limit window, then time one clean run (a throttled run is discarded and repeated)."""
    pause: float = PACE_S
    for i in range(12):
        await asyncio.sleep(pause)
        t = time.perf_counter()
        try:
            return await fn(*a, **k), time.perf_counter() - t
        except (LLMError, LLMUnavailable) as e:
            if i == 11:
                raise
            pause = _backoff(e)
            print(f"  waiting {pause:.0f}s: {e}", flush=True)
    raise LLMUnavailable("rate_limited", "no clean run")


# ---------------- 1 + 3: answers ----------------

def full_text(conn: Any, case_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT string_agg(text, ' ' ORDER BY id) FROM chunks WHERE case_id=%s AND role='body'", (case_id,))
        return (cur.fetchone() or [""])[0] or ""


COVERED = {"neutral", "scr"}  # every Supreme Court judgment 1950-2026 has these in the store


def cited_existence(report: dict[str, Any]) -> dict[str, int]:
    """matched = resolves to a real judgment. fabricated = a Supreme Court neutral/SCR citation (formats the store
    covers completely) that matches no judgment, or names a different case. Anything else that does not match
    (SCC, AIR, High Court reporters, name only) is 'outside coverage': possibly real, so not counted as fabricated
    (cf. Ovcharov 2026: reported hallucination rates depend on the reference store's coverage)."""
    from docketpilot.knowledge.citations import find_citations

    out = {"citations": 0, "matched_real_judgment": 0, "fabricated": 0, "outside_coverage": 0}
    for c in report.get("citations", []):
        out["citations"] += 1
        if c["verdict"] in ("VERIFIED", "PARTIAL"):
            out["matched_real_judgment"] += 1
            continue
        kinds = {x.kind for x in find_citations(c["raw"])}
        out["fabricated" if (kinds & COVERED or c["verdict"] == "CONFLICT") else "outside_coverage"] += 1
    out["unverifiable"] = out["fabricated"] + out["outside_coverage"]
    return out


async def answers(conn: Any, n: int) -> list[dict[str, Any]]:
    enc, base_llm = _enc(), get_llm()
    rows = []
    for q in QUESTIONS[:n]:
        row: dict[str, Any] = {"question": q}
        # DocketPilot, every call counted
        llm = Counting(base_llm)
        await asyncio.sleep(PACE_S)
        t = time.perf_counter()
        try:
            out = await _retry(chat.answer, conn, llm, [{"role": "user", "content": q}])
        except Exception as e:  # report, don't hide
            row["error"] = f"{type(e).__name__}: {e}"
            rows.append(row)
            continue
        tin, tout = llm.tokens()
        answer_out = llm.calls[0].output_tokens if llm.calls else 0
        row["docketpilot"] = {"seconds": round(time.perf_counter() - t, 1), "input_tokens": tin, "output_tokens": tout,
                              "llm_calls": len(llm.calls), "usd": cost(tin, tout),
                              "corrections": len(out.get("corrections", [])),
                              "answer": out["answer"],
                              # the answer as the user sees it: masking it again would turn the parties' names in
                              # public case names into PERSON_n and break the name/citation match
                              **cited_existence(await verify(conn, out["answer"], None))}
        # Baseline A (cost): same model fed whole judgments + the same statute sections
        res = rs.search(conn, q, rs.Filters(), mode="hybrid", k=12)
        case_ids = list(dict.fromkeys(h["case_id"] for h in res["hits"] if h["role"] == "body"))[:6]
        stat = chat.statute_sources(conn, q, q)
        prompt = (chat.PROMPTS / "chat_v1.md").read_text(encoding="utf-8") + "\n".join(full_text(conn, c) for c in case_ids) \
            + "\n".join(s["text"] or "" for s in stat) + q
        bin_ = len(enc.encode(prompt, disallowed_special=()))
        row["baseline_long_context"] = {"input_tokens": bin_, "output_tokens": answer_out, "usd": cost(bin_, answer_out),
                                        "judgments": len(case_ids)}
        # Baseline B (hallucination): same model, closed book
        await asyncio.sleep(PACE_S)
        t = time.perf_counter()
        try:
            r = await _retry(base_llm.complete, [
                {"role": "system", "content": "You are a legal research assistant for Indian advocates. Answer the "
                                              "question and support it with citations to Indian judgments (case name and "
                                              "citation)."},
                {"role": "user", "content": q}], reasoning_effort="medium", max_tokens=4000)
            rep = await verify(conn, r.text, None)
            row["baseline_closed_book"] = {"seconds": round(time.perf_counter() - t, 1), "answer": r.text, "input_tokens": r.input_tokens,
                                           "output_tokens": r.output_tokens, "usd": cost(r.input_tokens, r.output_tokens),
                                           **cited_existence(rep)}
        except Exception as e:
            row["baseline_closed_book"] = {"error": f"{type(e).__name__}: {e}"}
        print(json.dumps({k: v for k, v in row.items() if k != "question"})[:300], flush=True)
        rows.append(row)
    return rows


# ---------------- 2: document processing ----------------

GENERIC = ("Read this court document and list: the case number, the parties (petitioner/appellant and "
           "respondent), the court, and every date mentioned with what happened on it.")


def sample_docs(conn: Any, n: int) -> list[dict[str, Any]]:
    from docketpilot.ingestion.load import RAW, _hc_metadata_index

    idx = _hc_metadata_index()
    files = sorted((RAW / "hc_pdf").glob("*/*/*.txt"))
    random.Random(7).shuffle(files)
    out = []
    for f in files:
        meta = idx.get(f.stem)
        text = f.read_text(encoding="utf-8", errors="ignore")
        if not meta or len(text) < 3000:
            continue
        m = re.match(r"^\s*([^/]+?)\s*/\s*(\d+)\s*/\s*(\d{4})", meta["title"] or "")
        if not m:
            continue
        out.append({"file": f.name, "court": meta["court"] or meta["bench"], "text": text[:12000],
                    "gold_number": m.group(2).lstrip("0"), "gold_year": m.group(3)})
        if len(out) == n:
            break
    return out


async def processing(conn: Any, n: int) -> list[dict[str, Any]]:
    base_llm = get_llm()
    base_llm.rate_wait_s = 0  # type: ignore[attr-defined]  # a throttled run is retried by _timed, never timed
    rows = []
    for d in sample_docs(conn, n):
        row: dict[str, Any] = {"file": d["file"], "court": d["court"]}
        # DocketPilot
        counter = Counting(base_llm)
        casefile.get_llm = lambda c=counter: c  # type: ignore[misc]

        async def ours(text: str = d["text"], counter: Counting = counter) -> tuple[Any, Any, Any]:
            counter.calls.clear()
            cn = casefile.find_case_number(text)  # local, before masking
            red = pii.redact(text)
            return cn, red, await casefile.extract_info(red.text)

        try:
            (cn, red, info), secs = await _timed(ours)
            tin, tout = counter.tokens()
            ok = bool(cn and re.search(rf"\b0*{d['gold_number']}\b", cn.display) and d["gold_year"] in cn.display)
            row["docketpilot"] = {"seconds": round(secs, 2), "input_tokens": tin, "output_tokens": tout,
                                  "usd": cost(tin, tout), "events": len(info.get("events", [])), "case_number_correct": ok,
                                  "case_number": cn.display if cn else None, "names_sent_to_ai": 0}
        except Exception as e:
            row["docketpilot"] = {"error": f"{type(e).__name__}: {e}"}
            red = pii.redact(d["text"])
        # Baseline: whole unmasked text, generic prompt, default effort, free text
        try:
            r, secs = await _timed(base_llm.complete, [{"role": "user", "content": f"{GENERIC}\n\n{d['text']}"}],
                                   reasoning_effort="medium", max_tokens=6000)
            num_ok = bool(re.search(rf"\b0*{d['gold_number']}\s*(?:of|OF|/)\s*{d['gold_year']}\b", r.text))
            row["baseline"] = {"seconds": round(secs, 2), "input_tokens": r.input_tokens,
                               "output_tokens": r.output_tokens, "usd": cost(r.input_tokens, r.output_tokens),
                               "case_number_correct": num_ok, "names_sent_to_ai": len(red.mapping)}
        except Exception as e:
            row["baseline"] = {"error": f"{type(e).__name__}: {e}"}
        print(json.dumps(row)[:300], flush=True)
        rows.append(row)
    return rows


# ---------------- summary ----------------

def _mean(rows: list[dict[str, Any]], arm: str, key: str) -> float | None:
    vals = [r[arm][key] for r in rows if isinstance(r.get(arm), dict) and key in r[arm]]
    return statistics.mean(vals) if vals else None


def summarise(ans: list[dict[str, Any]], proc: list[dict[str, Any]]) -> dict[str, Any]:
    s: dict[str, Any] = {}
    dp, bl = _mean(ans, "docketpilot", "usd"), _mean(ans, "baseline_long_context", "usd")
    if dp and bl:
        s["cost_per_answer_usd"] = {"docketpilot": dp, "baseline_long_context": bl, "reduction_pct": 100 * (1 - dp / bl)}
    pd_, pb = _mean(proc, "docketpilot", "seconds"), _mean(proc, "baseline", "seconds")
    if pd_ and pb:
        s["document_processing_seconds"] = {"docketpilot": pd_, "baseline": pb, "speedup_pct": 100 * (1 - pd_ / pb)}
        s["document_processing_cost_usd"] = {"docketpilot": _mean(proc, "docketpilot", "usd"),
                                             "baseline": _mean(proc, "baseline", "usd")}
        s["case_number_accuracy"] = {
            arm: statistics.mean(float(r[arm]["case_number_correct"]) for r in proc if "case_number_correct" in r.get(arm, {}))
            for arm in ("docketpilot", "baseline")}
    for arm in ("docketpilot", "baseline_closed_book"):
        c = sum(r[arm]["citations"] for r in ans if "citations" in r.get(arm, {}))
        tot = {k: sum(r[arm].get(k, 0) for r in ans if "citations" in r.get(arm, {}))
               for k in ("matched_real_judgment", "fabricated", "outside_coverage", "unverifiable")}
        s.setdefault("citations", {})[arm] = {"total": c, **tot,
                                               "fabricated_rate": tot["fabricated"] / c if c else None,
                                               "unverifiable_rate": tot["unverifiable"] / c if c else None,
                                               "answers_with_citations": sum(1 for r in ans if r.get(arm, {}).get("citations"))}
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-questions", type=int, default=12)
    ap.add_argument("--n-docs", type=int, default=10)
    ap.add_argument("--only", choices=["processing", "answers"], help="run one experiment; keep the other's saved rows")
    args = ap.parse_args()
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    with connect() as conn:
        proc = asyncio.run(processing(conn, args.n_docs)) if args.only != "answers" else old.get("processing", [])
        ans = asyncio.run(answers(conn, args.n_questions)) if args.only != "processing" else old.get("answers", [])
    result = {"generated": datetime.now(UTC).isoformat(), "model": "openai/gpt-oss-120b (Groq)",
              "price_usd_per_m": {"input": 0.15, "output": 0.60}, "summary": summarise(ans, proc),
              "answers": ans, "processing": proc}
    OUT.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result["summary"], indent=1))


if __name__ == "__main__":
    main()
