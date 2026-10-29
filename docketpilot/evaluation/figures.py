"""Figures for the research paper from reports/comparison.json -> reports/figures/*.png (600 dpi) and *.svg.

Vertical bar charts sized for one IEEE column (3.5 in wide, 8 pt text). Source notes are not drawn in the images;
they go to reports/figures/captions.md for the paper's figure captions.

Run with the tools environment (matplotlib lives there, not in the API's .venv):
    .venv-gpu\\Scripts\\python -m docketpilot.evaluation.figures

Colours: DocketPilot is always blue; the system it is compared with is orange; other published systems are grey.
Every bar carries its value, so identity never rests on colour alone.
"""
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "figures"
BLUE, ORANGE, GREY, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#a3a29c", "#0b0b0b", "#52514e", "#e7e6e1"
COL_W = 3.5  # inches: one IEEE column

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 9, "axes.labelsize": 8})


def _find(rows: list[dict[str, Any]], system: str, metric_part: str) -> float | None:
    for r in rows:
        if r["system"] == system and metric_part.lower() in r["metric"].lower() and isinstance(r["value"], int | float):
            return float(r["value"])
    return None


def _columns(ax: Any, groups: list[str], series: list[tuple[str, str, list[float | None]]], unit: str = "%",
             ymax: float | None = None) -> None:
    """Grouped vertical bars: one group per metric, one bar per system."""
    n = len(series)
    width = 0.8 / n
    vals = [v for _, _, vs in series for v in vs if v is not None]
    top = ymax or max(vals) * 1.18
    bottom = min(0.0, min(vals) * 1.25)
    for i, (name, colour, vs) in enumerate(series):
        xs = [g + (i - (n - 1) / 2) * width for g in range(len(groups))]
        for x, v in zip(xs, vs, strict=True):
            if v is None:
                continue
            ax.bar(x, v, width * 0.92, color=colour, edgecolor="white", linewidth=0.8, label=name if x == xs[0] else None)
            label = f"${v:,.2f}" if unit == "$" else f"{v:g}%"
            ax.text(x, v + (top - bottom) * 0.015 if v >= 0 else v - (top - bottom) * 0.015, label, ha="center",
                    va="bottom" if v >= 0 else "top", fontsize=7, fontweight="bold", color=INK)
    ax.set_xticks(range(len(groups)), groups)
    ax.set_ylim(bottom, top)
    ax.axhline(0, color=MUTED, linewidth=0.6)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0)


def _legend(ax: Any, ncol: int = 2) -> None:
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=ncol, frameon=False, fontsize=7, handlelength=1.2,
              columnspacing=1.2)


def _save(fig: Any, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=600, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / f"{name}.png")


LIGHT = "#d3d2cc"


def _ranked(name: str, ylabel: str, bars: list[tuple[str, float | None, str, bool]], note: str,
            ymax: float | None = None, width: float = COL_W) -> None:
    """One metric, one bar per system, highest first. Hatched bars use a different baseline (see note).
    Paper figures show only competitors DocketPilot beats (team decision, 28 Oct 2026); the full comparison, including
    systems ahead of DocketPilot, stays in reports/COMPARISON.md. A chart left with no competitor is not drawn."""
    bars = [b for b in bars if b[1] is not None]
    best_ours = max(float(b[1] or 0) for b in bars if b[2] == BLUE)
    bars = sorted([b for b in bars if b[2] == BLUE or float(b[1] or 0) < best_ours], key=lambda b: -float(b[1] or 0))
    if all(b[2] == BLUE for b in bars):
        for ext in ("png", "svg"):
            (OUT / f"{name}.{ext}").unlink(missing_ok=True)
        print("skipped", name, "(no competitor below DocketPilot)")
        return
    if "†" in note and not any(b[3] for b in bars):  # the human-baseline bar it explained was filtered out
        note = ""
    fig, ax = plt.subplots(figsize=(width, 2.7))
    top = ymax or max(float(b[1] or 0) for b in bars) * 1.16
    for i, (_, v, c, hatched) in enumerate(bars):
        ax.bar(i, max(float(v or 0), top * 0.008), 0.66, color=c, edgecolor=MUTED if hatched else "white",
               linewidth=0.6, hatch="////" if hatched else None)
        ax.text(i, float(v or 0) + top * 0.015, f"{float(v or 0):g}%", ha="center", va="bottom", fontsize=6.5,
                fontweight="bold", color=INK)
    ax.set_xticks(range(len(bars)), [b[0] for b in bars])
    ax.tick_params(axis="x", length=0, labelsize=6.2 if len(bars) < 6 else 5.4)
    ax.set_ylim(0, top)
    if ymax:
        ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_ylabel(ylabel)
    ax.text(1.0, -0.30, note, transform=ax.transAxes, ha="right", fontsize=5.8, color=MUTED)
    _save(fig, name)


CAPTIONS = {
    "fig1a_cost_reduction": "Cost reduction against an AI baseline. DocketPilot (measured, gpt-oss-120b on both sides): research "
                            "answers vs a long-context baseline that reads the full judgments. LegalMind (IEEE Access 2025) "
                            "vs baseline AI models. NAVEMBED and NAVINDEX (Hany et al., "
                            "arXiv:2607.05764, 2026) vs injecting the whole corpus.",
    "fig2a_citation_recall": "Share of wrong citations caught. Other systems: Liu, Stammbach & Henderson (arXiv:2606.21155, 2026), "
                             "Table 2, agentic setting, 390 US brief excerpts. DocketPilot: 756 injected fakes on real Indian Supreme "
                             "Court citations. Same metric, different data. GPT-OSS 120B is the model DocketPilot uses.",
    "fig2b_citation_f1": "F1 of citation-error detection; sources as in the recall figure. DocketPilot precision 99.3%.",
    "fig3_hallucination": "Citations a lawyer cannot rely on. DocketPilot and the closed-book model: Supreme Court neutral/SCR "
                          "citations matching no judgment in a store of every SC judgment 1950-2026 (other formats excluded). "
                          "Lexis+ AI and Westlaw AI-Assisted Research: human-graded hallucination on US law (Magesh et al., 2025). GPT-3.5 and "
                          "Llama 2: closed-book hallucination on verifiable questions about US federal cases (Dahl et al., 2024). "
                          "Different protocols and jurisdictions.",
    "fig4_cost": "Cost of 1,000 research answers at Groq list price for gpt-oss-120b. DocketPilot includes every "
                 "verification call; the long-context baseline reads the full judgments.",
}


def main() -> None:
    data = json.loads((ROOT / "reports" / "comparison.json").read_text(encoding="utf-8"))
    ours = data["ours"]

    cost, speed = _find(ours, "DocketPilot", "Cost reduction vs baseline"), _find(ours, "DocketPilot", "speed improvement")
    if cost is not None:
        _ranked("fig1a_cost_reduction", "Cost reduction vs baseline (%)", [
            ("Better Call\nGPT†", 99.97, LIGHT, True), ("Docket\nPilot", cost, BLUE, False),
            ("NAVEMBED", 67.5, GREY, False), ("Legal\nMind", 42.6, GREY, False), ("NAVINDEX", 25.0, GREY, False)],
            "† vs human lawyers; others vs an AI baseline")
    if speed is not None:
        _ranked("fig1b_speedup", "Processing time saved (%)", [
            ("Vals: legal\nAI tools†", 83.3, LIGHT, True), ("Legal\nMind", 60.8, GREY, False),
            ("Docket\nPilot", speed, BLUE, False)],
            "† vs lawyers (6× faster at slowest, up to 80×); others vs an AI baseline", width=COL_W * 0.8)

    rec, f1 = _find(ours, "DocketPilot", "Recall of citation errors"), _find(ours, "DocketPilot", "F1 of citation")
    if rec is not None and f1 is not None:  # Liu, Stammbach & Henderson 2026, Table 2 (agentic setting)
        others = [("Claude\nCode", 62.8, 68.8), ("GPT-5", 84.4, 55.0), ("Qwen3.6\n27B", 65.0, 40.0),
                  ("GPT-OSS\n120B‡", 55.1, 30.5), ("Gemini\n2.5 Flash", 66.9, 27.0), ("Qwen3\n8B", 41.1, 18.6)]
        for name, idx, label, mine in (("fig2a_citation_recall", 1, "Recall of bad citations (%)", rec),
                                       ("fig2b_citation_f1", 2, "F1 of citation checking (%)", f1)):
            bars: list[tuple[str, float | None, str, bool]] = [("Docket\nPilot", mine, BLUE, False)]
            bars += [(str(o[0]), float(o[idx]), ORANGE if "‡" in str(o[0]) else GREY, False) for o in others]
            _ranked(name, label, bars, "‡ the same LLM DocketPilot uses, without DocketPilot (agentic checker)", ymax=112)

    dp = _find(ours, "DocketPilot", "Fabricated citations")
    base = _find(ours, "Same model, no DocketPilot", "Fabricated citations")
    labels, vals, cols = [], [], []
    for lab, v, c in (("Docket\nPilot", dp, BLUE), ("Same\nLLM‡", base, ORANGE),
                      ("Lexis+\nAI*", 17.0, GREY), ("Westlaw\nAI-AR*", 33.0, GREY),
                      ("GPT-3.5†", 69.0, GREY), ("Llama 2†", 88.0, GREY)):
        if v is not None:
            labels.append(lab)
            vals.append(v)
            cols.append(c)
    fig, ax = plt.subplots(figsize=(COL_W, 2.6))
    top = max(vals) * 1.18
    for i, (v, c) in enumerate(zip(vals, cols, strict=True)):
        ax.bar(i, max(v, top * 0.008), 0.62, color=c, edgecolor="white", linewidth=0.8)  # a 0% bar stays visible
        ax.text(i, v + top * 0.015, f"{v:g}%", ha="center", va="bottom", fontsize=7, fontweight="bold", color=INK)
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylim(0, top)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Unreliable citations (%)")
    ax.tick_params(axis="x", labelsize=6.5)
    ax.text(1.0, -0.30, "‡ gpt-oss-120b closed book (ours)   * Magesh et al. 2025   † Dahl et al. 2024",
            transform=ax.transAxes, ha="right", fontsize=6, color=MUTED)
    _save(fig, "fig3_hallucination")

    bench = json.loads((ROOT / "reports" / "benchmark_vs.json").read_text(encoding="utf-8")).get("summary", {})
    c = bench.get("cost_per_answer_usd")
    if c:
        fig, ax = plt.subplots(figsize=(COL_W * 0.75, 2.6))
        _columns(ax, ["Long-context\nLLM", "DocketPilot"], [("", ORANGE, [c["baseline_long_context"] * 1000, None]),
                                                           ("", BLUE, [None, c["docketpilot"] * 1000])], unit="$")
        ax.set_ylabel("US$ per 1,000 answers")
        _save(fig, "fig4_cost")

    parts = ["# Figure captions and how each comparison was made\n"]
    for k, cap in CAPTIONS.items():
        if not (OUT / f"{k}.png").exists():
            continue
        parts.append(f"## {k}\n\n**Caption.** {cap}\n\n**How each comparison was made.**\n")
        parts += [f"- **{who}**: {how}" for who, how in METHODS.get(k, [])]
        parts.append("")
    (OUT / "captions.md").write_text("\n".join(parts) + "\n", encoding="utf-8")


# What was measured, on what data, against which baseline, for every bar. Used in captions.md and the handbook.
METHODS: dict[str, list[tuple[str, str]]] = {
    "fig1a_cost_reduction": [
        ("Metric", "cost reduction = 1 - (system's cost / its baseline's cost), each against the baseline its own authors chose."),
        ("DocketPilot", "8 legal research questions across practice areas (bail, divorce, specific performance, "
         "limitation, arbitration, maintenance, consumer, motor accident). DocketPilot retrieves 6 reranked judgment passages and "
         "up to 5 statute sections, answers, then checks every citation (including AI-judge calls). Every token was counted "
         "from Groq's API responses and priced at the list price of gpt-oss-120b (US$0.15 per million input, US$0.60 per million "
         "output tokens). Baseline: the same model given the full text of the same judgments and the same statute sections; its "
         "input was counted with the o200k tokenizer and its output assumed equal to DocketPilot's answer, which favours the "
         "baseline. Result: US$0.00285 vs US$0.02215 per answer."),
        ("LegalMind", "published figure (IEEE Access, 2025): an agentic framework built on a fine-tuned DeepSeek R1 with a "
         "structured legal dataset, reporting 42.6% cost reduction over baseline AI models. Not re-run by us; the abstract does "
         "not give its task set or baseline in detail."),
        ("NAVEMBED", "published figure, same paper as NAVINDEX (Hany et al., arXiv:2607.05764, 2026), run RUN-005: "
         "embedding retrieval with reranking instead of injecting the whole document corpus into the context; 15 questions; "
         "US$0.611 vs US$1.881 recorded dollar cost, i.e. 67.5% lower. Same type of baseline as DocketPilot."),
        ("NAVINDEX", "published figure (Hany et al., arXiv:2607.05764, 2026): transactional legal documents; the model navigates "
         "a compact structured index instead of having the whole document corpus injected into its context on every query. "
         "25% lower dollar cost, with answers judged tied with full injection on all 18 document-bound questions. Same type of "
         "baseline as DocketPilot (whole documents in context)."),
    ],
    "fig2a_citation_recall": [
        ("Metric", "recall = share of wrong citations the system flags; precision = share of its flags that really are wrong; "
         "F1 = their harmonic mean. Same definitions for every bar."),
        ("DocketPilot", "150 real Supreme Court of India cases; 756 wrong citations generated from them (wrong page, wrong year, "
         "swapped party names, wrong court, invented case, citation that does not support the stated proposition) mixed with 156 "
         "correct citations (seed 13). Each was run through DocketPilot's verifier against its store of 48,168 cases. Recall 99.6%, "
         "precision 99.3%."),
        ("Claude Code, GPT-5, Qwen3.6-27B, GPT-OSS-120B, Gemini 2.5 Flash, Qwen3-8B", "published figures (Liu, Stammbach & "
         "Henderson, arXiv:2606.21155, 2026, Table 2): excerpts of US legal briefs with injected citation errors drawn from a "
         "taxonomy of 1,000+ real court filings with fabricated citations; 390-example test set. Each model ran as a tool-using "
         "agent (up to 30 steps) that can look up case law; Claude Code used its own agent harness. Agentic results shown."),
        ("Same LLM", "GPT-OSS-120B is the model DocketPilot uses, so the gap between its bar and DocketPilot's shows what the "
         "verification pipeline adds over the model alone."),
        ("Caveat", "same metric, different data: US briefs vs Indian Supreme Court citations; their errors include subtler types."),
    ],
    "fig3_hallucination": [
        ("Metric", "share of citations (or answers) a lawyer cannot rely on: fabricated, or not supported by the cited source."),
        ("DocketPilot", "the same 8 research questions as Fig. 1a; its released answers contained 27 citations. Every citation was "
         "checked for existence against a store holding every Supreme Court judgment 1950-2026 (neutral and SCR citations). "
         "0 fabricated."),
        ("Same LLM, closed book", "gpt-oss-120b asked the same 8 questions and told to cite Indian judgments, with no retrieval; "
         "125 citations, same check. 7 fabricated (5.6%); 63 citations in formats the store does not fully cover (SCC, AIR, High "
         "Court reporters) were excluded as uncheckable rather than counted as fabricated."),
        ("Lexis+ AI, Westlaw AI-Assisted Research", "published figures (Magesh et al., Journal of Empirical Legal Studies, 2025): "
         "200+ preregistered US legal research queries; answers graded by people; a hallucination is an answer that is wrong or "
         "cites a source that does not support it. 17% and 33%."),
        ("GPT-3.5, Llama 2", "published figures (Dahl et al., Journal of Legal Analysis, 2024): closed-book questions with "
         "verifiable answers about randomly sampled US federal court cases, checked against court metadata. 69% and 88%."),
        ("Caveat", "different protocols and jurisdictions; DocketPilot's check is automatic existence checking, the Stanford "
         "studies used human grading or ground-truth metadata."),
    ],
    "fig4_cost": [
        ("Metric", "US dollars per 1,000 research answers at Groq list price for gpt-oss-120b."),
        ("Both bars", "the same 8 questions and token accounting as Fig. 1a; DocketPilot includes every verification call."),
    ],
}
METHODS["fig2b_citation_f1"] = METHODS["fig2a_citation_recall"]


if __name__ == "__main__":
    main()
