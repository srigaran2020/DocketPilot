"""Comparison of DocketPilot with LegalMind and other legal AI systems -> reports/COMPARISON.md + reports/comparison.json.

Our numbers come from reports/benchmark_vs.json (this build, measured) and reports/evaluation.json (fake-citation,
privacy and retrieval benchmarks). Other systems' numbers are copied from their papers with the source. Most were
measured on different data and tasks; every row says how comparable it is. Nothing here is estimated for them.

    python -m docketpilot.evaluation.comparison
"""
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"

# Published figures. "same_metric" = the metric has the same definition as ours (still different data).
PUBLISHED: list[dict[str, Any]] = [
    {"system": "LegalMind (DeepSeek R1, agentic)", "metric": "Cost reduction vs baseline AI models", "value": 42.6, "unit": "%",
     "source": "LegalMind, IEEE Access 2025, DOI 10.1109/ACCESS.2025.3586781, abstract",
     "comparable": "Same metric name; their baseline and tasks are not public in the abstract."},
    {"system": "LegalMind (DeepSeek R1, agentic)", "metric": "Document processing speed improvement vs baseline AI models",
     "value": 60.8, "unit": "%", "source": "DOI 10.1109/ACCESS.2025.3586781 (IEEE Access, 2025), abstract",
     "comparable": "Same metric name; their documents and baseline are not public in the abstract."},
    {"system": "NAVEMBED (Hany et al., 2026)", "metric": "Cost reduction vs whole-corpus injection", "value": 67.5, "unit": "%",
     "source": "arXiv:2607.05764, RUN-005: US$0.611 vs US$1.881", "comparable": "Same baseline type as DocketPilot (full documents in context)."},
    {"system": "NAVINDEX (Hany et al., 2026)", "metric": "Cost reduction vs whole-corpus injection", "value": 25, "unit": "%",
     "source": "arXiv:2607.05764: US$1.21 vs US$1.61", "comparable": "Same baseline type as DocketPilot."},
    {"system": "Lexis+ AI", "metric": "Hallucination rate (legal research answers)", "value": 17, "unit": "%",
     "source": "Magesh et al., 'Hallucination-Free?', arXiv:2405.20362 (Stanford RegLab/HAI); figures as reported by LawSites, June 2024",
     "comparable": "US law, 200+ preregistered queries, human-graded; ours is an automatic existence check on Indian law."},
    {"system": "Westlaw AI-Assisted Research", "metric": "Hallucination rate (legal research answers)", "value": 33, "unit": "%",
     "source": "Magesh et al., arXiv:2405.20362; LawSites, June 2024", "comparable": "As above."},
    {"system": "Lexis+ AI", "metric": "Accurate answers", "value": 65, "unit": "%",
     "source": "Magesh et al., arXiv:2405.20362; LawSites, June 2024", "comparable": "Human-graded accuracy; not measured for DocketPilot."},
    {"system": "Westlaw AI-Assisted Research", "metric": "Accurate answers", "value": 42, "unit": "%",
     "source": "Magesh et al., arXiv:2405.20362; LawSites, June 2024", "comparable": "As above."},
    {"system": "Ask Practical Law AI", "metric": "Accurate answers", "value": 20, "unit": "%",
     "source": "Magesh et al., J. Empirical Legal Studies 22 (2025), DOI 10.1111/jels.12413 (text: 19% -> 20% after re-grading)",
     "comparable": "Human-graded accuracy; not measured for DocketPilot."},
    {"system": "GPT-3.5 (closed book)", "metric": "Hallucination rate (legal queries)", "value": 69, "unit": "%",
     "source": "Dahl, Magesh, Suzgun & Ho, 'Large Legal Fictions', J. Legal Analysis 16 (2024), arXiv:2401.01301",
     "comparable": "Closed-book model on verifiable questions about US federal cases; like our closed-book baseline, other law."},
    {"system": "Llama 2 (closed book)", "metric": "Hallucination rate (legal queries)", "value": 88, "unit": "%",
     "source": "Dahl et al. 2024, arXiv:2401.01301", "comparable": "As above."},
    {"system": "Harvey Assistant", "metric": "Document Q&A score (lawyer baseline 70.1)", "value": 94.8, "unit": "%",
     "source": "Vals Legal AI Report (VLAIR), 27 Feb 2025", "comparable": "Task accuracy vs lawyers; not a DocketPilot metric."},
    {"system": "CoCounsel", "metric": "Document Q&A score (lawyer baseline 70.1)", "value": 89.6, "unit": "%",
     "source": "Vals Legal AI Report (VLAIR), 27 Feb 2025", "comparable": "As above."},
    {"system": "GPT-5, agentic citation checker", "metric": "Recall of citation errors (hallucination detection)", "value": 84.4,
     "unit": "%", "source": "Liu, Stammbach & Henderson, 'Who Checks the Citations?', arXiv:2606.21155 (2026)",
     "comparable": "Same metric (share of bad citations caught); their 1,300 US brief excerpts are harder and more varied than our fakes."},
    {"system": "GPT-5, agentic citation checker", "metric": "F1 of citation-error detection", "value": 55.0, "unit": "%",
     "source": "arXiv:2606.21155", "comparable": "Same metric; different data (see above)."},
    {"system": "Best of 21 LLMs, closed book", "metric": "Citation retrieval/completion score", "value": 7, "unit": "/100 (below)",
     "source": "Chen, Yin & Zhou, 'LegalCiteBench', arXiv:2605.10186 (ICML 2026)",
     "comparable": "Shows why closed-book models cannot be trusted with citations; misleading-answer rate >94% for 20 of 21 models."},
    {"system": "4 commercial LLMs (Ukrainian law)", "metric": "Hallucinated citations, sparse vs dense reference store",
     "value": "15-21 vs ~0.1-1.1", "unit": "%", "source": "Ovcharov, 'Citation Grounding Measures the Oracle', arXiv:2606.00898 (2026)",
     "comparable": "Methodological: the measured rate depends on the reference store's coverage. We therefore count only "
                   "formats our store covers completely as fabricated."},
    {"system": "Falkor-IRAC (Indian judicial AI)", "metric": "Verified answers via graph verifier", "value": "qualitative",
     "unit": "", "source": "Bose, arXiv:2605.14665 (2026); proof of concept on 51 SC judgments",
     "comparable": "Closest Indian system; reports no hallucination or retrieval metric to compare."},
]


def _load(name: str) -> dict[str, Any]:
    p = REPORTS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build() -> dict[str, Any]:
    bench, ev = _load("benchmark_vs.json"), _load("evaluation.json")
    s = bench.get("summary", {})
    ours: list[dict[str, Any]] = []

    def add(metric: str, value: Any, unit: str, how: str) -> None:
        if value is not None:
            ours.append({"system": "DocketPilot", "metric": metric, "value": value, "unit": unit, "how": how})

    cost = s.get("cost_per_answer_usd") or {}
    add("Cost reduction vs baseline AI model (research answer)", round(cost["reduction_pct"], 1) if cost else None, "%",
        f"gpt-oss-120b on Groq both sides; DocketPilot ${cost.get('docketpilot', 0):.5f} incl. every verifier call vs "
        f"long-context baseline ${cost.get('baseline_long_context', 0):.5f} per answer")
    speed = s.get("document_processing_seconds") or {}
    add("Document processing speed improvement vs baseline AI model", round(speed["speedup_pct"], 1) if speed else None, "%",
        f"{speed.get('docketpilot', 0):.1f}s vs {speed.get('baseline', 0):.1f}s per real High Court judgment, same model, "
        "fresh rate-limit window per run")
    dcost = s.get("document_processing_cost_usd") or {}
    if dcost.get("docketpilot") and dcost.get("baseline"):
        add("Document processing cost reduction", round(100 * (1 - dcost["docketpilot"] / dcost["baseline"]), 1), "%",
            "same documents as above")
    acc = s.get("case_number_accuracy") or {}
    add("Case number read correctly (real HC judgments)", round(100 * acc["docketpilot"], 1) if acc else None, "%",
        f"baseline model {100 * acc.get('baseline', 0):.0f}%")
    cit = (s.get("citations") or {})
    # Runs before the fix of 28 Oct re-masked DocketPilot's answer before checking it (case names became PERSON_n),
    # so its citation rows are only trusted when the run saved the answer text (the fixed version).
    fixed = any("answer" in (r.get("docketpilot") or {}) for r in bench.get("answers", []))
    for arm, label in (("docketpilot", "DocketPilot"), ("baseline_closed_book", "Same model, no DocketPilot")):
        c = cit.get(arm) or {}
        if arm == "docketpilot" and not fixed:
            continue
        if c.get("total"):
            ours.append({"system": label, "metric": "Fabricated citations in answers", "value": round(100 * c["fabricated_rate"], 1),
                         "unit": "%", "how": f"{c['fabricated']} of {c['total']} citations; {c['outside_coverage']} outside the "
                                                 "store's coverage (not counted)"})
    fake = (ev.get("fake_citations") or {}).get("overall") or {}
    if fake:
        add("Recall of citation errors (fake-citation benchmark)", round(100 * fake["recall"], 1), "%",
            f"{fake.get('fakes', 756)} injected fakes, {fake.get('reals', 156)} real citations; precision {100 * fake['precision']:.1f}%")
        add("F1 of citation-error detection", round(100 * fake["f1"], 1), "%", "same benchmark")
    pii = (ev.get("pii") or {}).get("heldout_with_ner") or {}
    if pii:
        add("Personal data hidden from the AI (held-out recall)", round(100 * pii["recall"], 1), "%", "synthetic Indian PII")
    ret = (ev.get("retrieval") or {}).get("hybrid_rerank") or {}
    if ret:
        add("Retrieval Recall@5 (hybrid + rerank)", round(100 * ret["recall@5"], 1), "%", "headnote -> own judgment, s.138 SC")
    out = {"ours": ours, "published": PUBLISHED, "benchmark_generated": bench.get("generated")}
    (REPORTS / "comparison.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def markdown(data: dict[str, Any]) -> str:
    rows = ["| System | Metric | Value | How measured |", "|---|---|---|---|"]
    rows += [f"| {r['system']} | {r['metric']} | **{r['value']}{r['unit']}** | {r['how']} |" for r in data["ours"]]
    pub = ["| System | Metric | Value | Source | Comparable? |", "|---|---|---|---|---|"]
    pub += [f"| {r['system']} | {r['metric']} | {r['value']}{r['unit']} | {r['source']} | {r['comparable']} |"
            for r in data["published"]]
    return "\n".join([
        "# DocketPilot compared with LegalMind and other legal AI systems", "",
        f"Our numbers: measured on this build (benchmark run {data.get('benchmark_generated') or 'n/a'}). "
        "Other systems: copied from their papers. Different datasets and tasks unless the last column says otherwise; "
        "do not present a cross-paper difference as a head-to-head result.", "",
        "## DocketPilot (measured)", "", *rows, "",
        "## Published results of other systems", "", *pub, "",
        "## How to read this", "",
        "- **Same metric as LegalMind**: cost reduction and document-processing speed improvement over a baseline AI model. "
        "Our baseline is the same LLM without DocketPilot's pipeline, so the gain comes from the system design.",
        "- **Hallucination**: Stanford's figures are human-graded answer errors on US law; ours count citations that "
        "match no real judgment. Both are 'citations a lawyer cannot rely on', but the protocols differ.",
        "- **Citation-error detection**: same definition as Liu et al. (recall/F1 of bad citations caught); our fakes are "
        "simpler (wrong page/year/court, swapped names, invented cases, wrong proposition).",
        "- Re-run: `python -m docketpilot.evaluation.benchmark_vs` then `python -m docketpilot.evaluation.comparison`.", ""])


def chart_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Bars for the comparison page: one row per bar, grouped by chart. 'role': ours | named | other."""
    ours = data["ours"]

    def find(system: str, part: str) -> float | None:
        return next((float(r["value"]) for r in ours if r["system"] == system and part.lower() in r["metric"].lower()
                     and isinstance(r["value"], int | float)), None)

    rows: list[dict[str, Any]] = []

    def bar(chart: str, label: str, system: str, value: float | None, role: str, unit: str = "%") -> None:
        if value is not None:
            rows.append({"bar": f"{chart}:{len(rows)}", "chart": chart, "label": label, "system": system,
                         "value": round(value, 4), "unit": unit, "role": role})

    bar("legalmind", "Cost reduction", "LegalMind", 42.6, "named")
    bar("legalmind", "Cost reduction", "DocketPilot", find("DocketPilot", "Cost reduction vs baseline"), "ours")
    bar("legalmind", "Processing speed-up", "LegalMind", 60.8, "named")
    bar("legalmind", "Processing speed-up", "DocketPilot", find("DocketPilot", "speed improvement"), "ours")
    bar("checking", "Recall", "GPT-5 agentic checker", 84.4, "named")
    bar("checking", "Recall", "DocketPilot", find("DocketPilot", "Recall of citation errors"), "ours")
    bar("checking", "F1", "GPT-5 agentic checker", 55.0, "named")
    bar("checking", "F1", "DocketPilot", find("DocketPilot", "F1 of citation"), "ours")
    bar("hallucination", "Fabricated citations", "DocketPilot", find("DocketPilot", "Fabricated citations"), "ours")
    bar("hallucination", "Fabricated citations", "Same LLM, closed book",
        find("Same model, no DocketPilot", "Fabricated citations"), "named")
    bar("hallucination", "Hallucination (human-graded, US law)", "Westlaw AI-Assisted Research", 33.0, "other")
    bar("hallucination", "Hallucination (human-graded, US law)", "Lexis+ AI", 17.0, "other")
    bar("hallucination", "Hallucination (closed book, US law)", "GPT-3.5", 69.0, "other")
    bar("hallucination", "Hallucination (closed book, US law)", "Llama 2", 88.0, "other")
    bench = _load("benchmark_vs.json").get("summary", {})
    c = bench.get("cost_per_answer_usd")
    if c:
        bar("cost", "US$ per 1,000 answers", "Long-context LLM", c["baseline_long_context"] * 1000, "named", "$")
        bar("cost", "US$ per 1,000 answers", "DocketPilot", c["docketpilot"] * 1000, "ours", "$")
    return rows


def write_dashboard_files(data: dict[str, Any]) -> None:
    out = REPORTS / "dashboard"
    out.mkdir(exist_ok=True)
    measured = [{"key": f"m{i}", **{k: (str(v) if k == "value" else v) for k, v in r.items()}} for i, r in enumerate(data["ours"])]
    published = [{"key": f"p{i}", **{k: str(v) for k, v in r.items()}} for i, r in enumerate(data["published"])]
    for name, rows in (("measured", measured), ("published", published), ("charts", chart_rows(data))):
        (out / f"{name}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


def main() -> None:
    data = build()
    write_dashboard_files(data)
    (REPORTS / "COMPARISON.md").write_text(markdown(data), encoding="utf-8")
    print(markdown(data))


if __name__ == "__main__":
    main()
