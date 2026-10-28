"""Figures for the research paper from reports/comparison.json -> reports/figures/*.png (300 dpi) and *.svg.

Run with the tools environment (matplotlib lives there, not in the API's .venv):
    .venv-gpu\\Scripts\\python -m docketpilot.evaluation.figures

Colours: DocketPilot is always slot 1 (blue); a second named system is slot 2 (orange); other systems are neutral
grey so the reader's eye goes to the comparison that matters. Values are printed on the bars (no colour-only
identity). Every figure carries a footnote saying how comparable the numbers are.
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

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False})


def _find(rows: list[dict[str, Any]], system: str, metric_part: str) -> float | None:
    for r in rows:
        if r["system"] == system and metric_part.lower() in r["metric"].lower() and isinstance(r["value"], int | float):
            return float(r["value"])
    return None


def _bars(ax: Any, labels: list[str], values: list[float], colours: list[str], unit: str = "%") -> None:
    y = range(len(labels))
    ax.barh(list(y), values, color=colours, height=0.55, edgecolor="white", linewidth=2)
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.axvline(0, color=MUTED, linewidth=0.8)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    span = max(abs(v) for v in values) or 1
    for i, v in enumerate(values):
        ax.text(v + (0.015 * span if v >= 0 else -0.015 * span), i, f"{v:g}{unit}", va="center",
                ha="left" if v >= 0 else "right", color=INK, fontsize=10, fontweight="bold")


def _save(fig: Any, name: str, note: str) -> None:
    import textwrap

    fig.text(0.01, -0.13, "\n".join(textwrap.wrap(note, 125)), fontsize=7.5, color=MUTED, ha="left", va="top")
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / f"{name}.png")


def main() -> None:
    data = json.loads((ROOT / "reports" / "comparison.json").read_text(encoding="utf-8"))
    ours = data["ours"]

    # Fig 1: the two metrics LegalMind reports, same definitions.
    cost = _find(ours, "DocketPilot", "Cost reduction vs baseline")
    speed = _find(ours, "DocketPilot", "speed improvement")
    if cost is not None and speed is not None:
        fig, ax = plt.subplots(figsize=(7.2, 3.0))
        labels = ["Cost reduction\nLegalMind", "Cost reduction\nDocketPilot", "Processing speed-up\nLegalMind",
                  "Processing speed-up\nDocketPilot"]
        _bars(ax, labels, [42.6, cost, 60.8, speed], [ORANGE, BLUE, ORANGE, BLUE])
        ax.set_xlabel("Improvement over a baseline AI model (%)")
        ax.set_title("Same metrics as LegalMind (IEEE Access, 2025)", loc="left", fontsize=12, color=INK)
        _save(fig, "fig1_vs_legalmind",
              "LegalMind: published figures (DeepSeek R1; baseline and data not public). DocketPilot: measured, gpt-oss-120b both arms; "
              "cost = research answers vs long-context baseline; speed = real High Court judgments vs plain-LLM reading.")

    # Fig 2: catching bad citations (same metric definitions as Liu et al. 2026).
    rec, f1 = _find(ours, "DocketPilot", "Recall of citation errors"), _find(ours, "DocketPilot", "F1 of citation")
    if rec is not None and f1 is not None:
        fig, ax = plt.subplots(figsize=(7.2, 2.8))
        _bars(ax, ["Recall\nGPT-5 agentic checker", "Recall\nDocketPilot", "F1\nGPT-5 agentic checker", "F1\nDocketPilot"],
              [84.4, rec, 55.0, f1], [ORANGE, BLUE, ORANGE, BLUE])
        ax.set_xlim(0, 112)
        ax.set_xlabel("Bad citations caught (%)")
        ax.set_title("Citation-error detection", loc="left", fontsize=12, color=INK)
        _save(fig, "fig2_citation_checking",
              "GPT-5: Liu, Stammbach & Henderson, arXiv:2606.21155 (1,300 US brief excerpts). DocketPilot: 756 injected fakes + 156 real "
              "Indian SC citations (wrong page/year/court, swapped names, invented, wrong proposition). Same metric, different data.")

    # Fig 3: citations a lawyer cannot rely on.
    rows: list[tuple[str, float, str]] = []
    dp = _find(ours, "DocketPilot", "Fabricated citations")
    base = _find(ours, "Same model, no DocketPilot", "Fabricated citations")
    if dp is not None:
        rows.append(("DocketPilot (measured)", dp, BLUE))
    if base is not None:
        rows.append(("Same LLM, no DocketPilot\n(measured, closed book)", base, ORANGE))
    rows += [("Westlaw AI-Assisted Research\n(Magesh et al.)", 33.0, GREY), ("Lexis+ AI (Magesh et al.)", 17.0, GREY)]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    _bars(ax, [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows])
    ax.set_xlabel("Citations a lawyer cannot rely on (%)")
    ax.set_title("Hallucinated citations", loc="left", fontsize=12, color=INK)
    _save(fig, "fig3_hallucination",
          "DocketPilot and closed-book LLM: SC neutral/SCR citations matching no judgment in a store of every SC judgment 1950-2026 "
          "(citations outside that coverage excluded). Lexis+/Westlaw: human-graded hallucination on US law (Stanford RegLab, 2024). "
          "Different protocols.")

    # Fig 4: cost per answer.
    bench = json.loads((ROOT / "reports" / "benchmark_vs.json").read_text(encoding="utf-8")).get("summary", {})
    c = bench.get("cost_per_answer_usd")
    if c:
        fig, ax = plt.subplots(figsize=(7.2, 2.2))
        _bars(ax, ["Long-context LLM\n(reads whole judgments)", "DocketPilot\n(incl. verification calls)"],
              [round(c["baseline_long_context"] * 1000, 2), round(c["docketpilot"] * 1000, 2)], [ORANGE, BLUE], unit="")
        ax.set_xlabel("US$ per 1,000 research answers (Groq list price, gpt-oss-120b)")
        ax.set_title("Cost per research answer", loc="left", fontsize=12, color=INK)
        _save(fig, "fig4_cost", "Tokens counted from API responses (DocketPilot) and with the o200k tokenizer (baseline input); "
                                "baseline output assumed equal to DocketPilot's answer.")


if __name__ == "__main__":
    main()
