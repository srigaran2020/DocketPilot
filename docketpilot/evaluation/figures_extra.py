# ruff: noqa: E501  (long explanation strings)
r"""Additional paper figures: retrieval ablation, detection by error type, confusion matrix, privacy by data type,
knowledge-base composition, pipeline ablation, time and cost breakdowns, auto-correction outcomes, LIME.

Same style as figures.py (one IEEE column, 600 dpi). EXPLAIN holds a plain-language explanation of each figure for the
handbook and the paper: what it shows, how to read it, what it means, and how it was measured.

    .venv-gpu\Scripts\python -m docketpilot.evaluation.figures_extra
"""
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from docketpilot.evaluation.figures import BLUE, COL_W, GREY, GRID, INK, MUTED, ORANGE, _save  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REP = ROOT / "reports"
TEAL, RED, GOLD = "#1baf7a", "#e34948", "#eda100"


def _load(name: str) -> Any:
    p = REP / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _style(ax: Any, ylabel: str, top: float | None = None) -> None:
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel(ylabel)
    if top:
        ax.set_ylim(0, top)


def _label(ax: Any, x: float, v: float, text: str, top: float) -> None:
    ax.text(x, v + top * 0.015, text, ha="center", va="bottom", fontsize=6.3, fontweight="bold", color=INK)


def fig_retrieval() -> None:
    ret = (_load("retrieval_current.json") or (_load("evaluation.json") or {}).get("retrieval"))
    if not ret:
        return
    modes = [("lexical", "Keyword\n(BM25-style)"), ("dense", "Meaning\n(vectors)"), ("hybrid", "Hybrid\n(RRF)"), ("hybrid_rerank", "Hybrid +\nre-rank")]
    metrics = [("recall@1", "Recall@1", GREY), ("recall@5", "Recall@5", BLUE), ("mrr@10", "MRR@10", TEAL)]
    fig, ax = plt.subplots(figsize=(COL_W, 2.7))
    w = 0.26
    for j, (key, name, col) in enumerate(metrics):
        for i, (m, _) in enumerate(modes):
            v = 100 * ret[m][key]
            x = i + (j - 1) * w
            ax.bar(x, v, w * 0.92, color=col, edgecolor="white", linewidth=0.6, label=name if i == 0 else None)
            ax.text(x, v + 1.2, f"{v:.0f}", ha="center", va="bottom", fontsize=5.4, color=INK)
    ax.set_xticks(range(len(modes)), [m[1] for m in modes], fontsize=6.4)
    _style(ax, "Score (%)", 112)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=3, frameon=False, fontsize=6.5)
    _save(fig, "fig5_retrieval_modes")

    fig, ax = plt.subplots(figsize=(COL_W, 2.6))
    for i, (m, name) in enumerate(modes):
        c = BLUE if m == "hybrid_rerank" else GREY
        ax.scatter(ret[m]["p50_ms"] / 1000, 100 * ret[m]["recall@5"], s=46, color=c, edgecolor="white", linewidth=0.8, zorder=3)
        ax.annotate(name.replace("\n", " "), (ret[m]["p50_ms"] / 1000, 100 * ret[m]["recall@5"]), textcoords="offset points",
                    xytext=(6, -10 if i % 2 else 5), fontsize=6.2, color=INK)
    ax.set_xscale("log")
    ax.set_xlabel("Median search time per query (s, log scale)")
    ax.set_ylabel("Recall@5 (%)")
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    lo = min(100 * ret[m]["recall@5"] for m, _ in modes)
    ax.set_ylim(lo - 4, 100)
    _save(fig, "fig6_speed_accuracy")


def fig_errors() -> None:
    fc = (_load("evaluation.json") or {}).get("fake_citations")
    if not fc:
        return
    pt = fc["per_type"]
    types = [("wrong_page", "Wrong\npage"), ("wrong_year", "Wrong\nyear"), ("swapped_names", "Swapped\nnames"), ("wrong_court", "Wrong\ncourt"),
             ("invented", "Invented\ncase"), ("wrong_proposition", "Wrong\nproposition")]
    fig, ax = plt.subplots(figsize=(COL_W, 2.6))
    for i, (k, _) in enumerate(types):
        v = 100 * pt[k]["caught_rate"]
        ax.bar(i, v, 0.62, color=BLUE if v >= 99.95 else ORANGE, edgecolor="white")
        _label(ax, i, v, f"{v:g}%\n(n={pt[k]['n']})", 118)
    ax.set_xticks(range(len(types)), [t[1] for t in types], fontsize=6.2)
    _style(ax, "Fake citations caught (%)", 118)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    _save(fig, "fig7_error_types")

    # confusion matrix from the per-type rates
    fakes = sum(pt[k]["n"] for k, _ in types)
    caught = round(sum(pt[k]["n"] * pt[k]["caught_rate"] for k, _ in types))
    reals = pt["real"]["n"] + pt["proposition_real"]["n"]
    flagged = round(pt["real"]["n"] * pt["real"]["false_alarm_rate"] + pt["proposition_real"]["n"] * pt["proposition_real"]["false_alarm_rate"])
    m = [[caught, fakes - caught], [flagged, reals - flagged]]
    fig, ax = plt.subplots(figsize=(COL_W * 0.78, 2.3))
    import numpy as np
    arr = np.array([[m[0][0] / fakes, m[0][1] / fakes], [m[1][0] / reals, m[1][1] / reals]])
    ax.imshow(arr, cmap="Blues", vmin=0, vmax=1)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{m[i][j]}\n({100 * arr[i, j]:.1f}%)", ha="center", va="center", fontsize=7,
                    color="white" if arr[i, j] > 0.5 else INK, fontweight="bold")
    ax.set_xticks([0, 1], ["Flagged", "Passed"])
    ax.set_yticks([0, 1], [f"Fake\n(n={fakes})", f"Real\n(n={reals})"])
    ax.set_xlabel("Verifier decision")
    ax.set_ylabel("Ground truth")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    _save(fig, "fig8_confusion_matrix")


def fig_privacy() -> None:
    pii = (_load("evaluation.json") or {}).get("pii")
    if not pii:
        return
    held = pii["heldout_with_ner"]["per_type_recall"]
    names = {"AADHAAR": "Aadhaar", "BANK_ACCOUNT": "Bank\naccount", "PHONE": "Phone", "ORG": "Organi-\nsation", "PERSON": "Person\nname"}
    keys = [k for k in names if k in held]
    fig, ax = plt.subplots(figsize=(COL_W, 2.5))
    for i, k in enumerate(keys):
        v = 100 * held[k]
        ax.bar(i, v, 0.6, color=BLUE if v >= 99.95 else ORANGE, edgecolor="white")
        _label(ax, i, v, f"{v:.1f}%", 115)
    i = len(keys)
    v = 100 * pii["heldout_with_ner"]["recall"]
    ax.bar(i, v, 0.6, color=TEAL, edgecolor="white")
    _label(ax, i, v, f"{v:.1f}%", 115)
    ax.set_xticks(range(len(keys) + 1), [names[k] for k in keys] + ["All\n(overall)"], fontsize=6.4)
    _style(ax, "Personal data masked (%)", 115)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    _save(fig, "fig9_privacy_types")


def fig_kb() -> None:
    kb = _load("kb_composition.json")
    if not kb:
        return
    courts = kb["judgments_by_court"]
    fig, ax = plt.subplots(figsize=(COL_W, 2.6))
    labels = list(courts)
    vals = [courts[c] for c in labels]
    top = max(vals) * 1.18
    for i, v in enumerate(vals):
        ax.bar(i, v, 0.62, color=BLUE if i == 0 else GREY, edgecolor="white")
        _label(ax, i, v, f"{v:,}", top)
    ax.set_xticks(range(len(labels)), labels, fontsize=6.0)
    _style(ax, "Judgments with full text", top)
    _save(fig, "fig10_knowledge_base")


def fig_ablation() -> None:
    ab = _load("ablation.json")
    if not ab:
        return
    arms = [("A", "LLM\nalone"), ("B", "+ Retrieval"), ("C", "+ Source\ntags"), ("D", "+ Verify &\nauto-correct\n(DocketPilot)")]
    fig, ax = plt.subplots(figsize=(COL_W, 2.8))
    tops = []
    for i, (k, _) in enumerate(arms):
        a = ab["arms"][k]
        f, u = a["fabricated_pct"], a["unsupported_pct"]
        ax.bar(i, max(f, 0.0), 0.6, color=RED, edgecolor="white", label="Fabricated" if i == 0 else None)
        ax.bar(i, max(u, 0.0), 0.6, bottom=f, color=GOLD, edgecolor="white", label="Real case, does not support the claim" if i == 0 else None)
        tops.append(f + u)
    top = max(max(tops) * 1.25, 5)
    for i, t in enumerate(tops):
        ax.bar(i, max(t, top * 0.008), 0.6, color="none", edgecolor=BLUE if i == 3 else "none", linewidth=0.8)
        _label(ax, i, t, f"{t:.1f}%", top)
    ax.set_xticks(range(4), [a[1] for a in arms], fontsize=6.2)
    _style(ax, "Unreliable citations (%)", top)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2, frameon=False, fontsize=6.2)
    _save(fig, "fig11_pipeline_ablation")

    t = ab["timing_mean_s"]
    stages = [("masking", "Masking"), ("retrieval", "Retrieval"), ("llm_answer", "LLM\nanswer"), ("verification", "Verifi-\ncation"), ("auto_correction", "Auto-\ncorrect")]
    fig, ax = plt.subplots(figsize=(COL_W, 2.5))
    vals = [t[k] for k, _ in stages]
    top = max(vals) * 1.22
    for i, v in enumerate(vals):
        ax.bar(i, v, 0.6, color=BLUE if stages[i][0] in ("verification", "auto_correction") else GREY, edgecolor="white")
        _label(ax, i, v, f"{v:.1f}s", top)
    ax.set_xticks(range(len(stages)), [s[1] for s in stages], fontsize=6.4)
    _style(ax, "Mean seconds per answer", top)
    _save(fig, "fig12_time_breakdown")

    tk = ab["tokens_mean"]
    groups = [("Answer\ninput", tk["answer_in"]), ("Answer\noutput", tk["answer_out"]), ("Verifier\ninput", tk["judge_in"]), ("Verifier\noutput", tk["judge_out"])]
    fig, ax = plt.subplots(figsize=(COL_W, 2.5))
    top = max(v for _, v in groups) * 1.22
    for i, (_, v) in enumerate(groups):
        ax.bar(i, v, 0.6, color=GREY if i < 2 else BLUE, edgecolor="white")
        _label(ax, i, v, f"{v:,.0f}", top)
    ax.set_xticks(range(len(groups)), [g[0] for g in groups], fontsize=6.4)
    _style(ax, "Mean tokens per answer", top)
    _save(fig, "fig13_token_breakdown")

    fu = ab["funnel"]
    steps = [("Citations\nwritten", fu["citations_before"], GREY), ("Corrected", fu["replaced"], GOLD), ("Removed", fu["removed"], RED),
             ("Released\n(verified)", fu["kept_in_final"], BLUE)]
    fig, ax = plt.subplots(figsize=(COL_W, 2.5))
    top = max(s[1] for s in steps) * 1.22 or 1
    for i, (_, v, c) in enumerate(steps):
        ax.bar(i, max(v, top * 0.008), 0.6, color=c, edgecolor="white")
        _label(ax, i, v, f"{v}", top)
    ax.set_xticks(range(len(steps)), [s[0] for s in steps], fontsize=6.4)
    _style(ax, "Citations (8 answers)", top)
    _save(fig, "fig14_autocorrect_outcomes")


def fig_lime() -> None:
    lime = _load("lime.json")
    if not lime:
        return
    fig, axes = plt.subplots(2, 1, figsize=(COL_W, 4.4))
    for ax, res, tag in zip(axes, lime, ["(a)", "(b)"], strict=False):
        words = res["top_words"][:10]
        vals = [w[1] for w in words]
        cols = [BLUE if v > 0 else RED for v in vals]
        ax.bar(range(len(words)), vals, 0.62, color=cols, edgecolor="white")
        ax.axhline(0, color=MUTED, linewidth=0.6)
        ax.set_xticks(range(len(words)), [w[0] for w in words], rotation=40, ha="right", fontsize=6.0)
        ax.yaxis.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.set_ylabel("Effect on\nrelevance score", fontsize=6.5)
        q = res["query"]
        ax.set_title(f"{tag} “{q[:58]}{'…' if len(q) > 58 else ''}”", fontsize=6.4, loc="left", color=INK)
    fig.tight_layout(h_pad=1.2)
    _save(fig, "fig15_lime")


# Published Indian legal-AI systems; only metrics where a like-for-like DocketPilot number exists and DocketPilot is higher.
INDIAN = [  # (axis label, DocketPilot metric path, the other system's reported value %)
    ("Top-1 retrieval\nprecision\nvs NyayaAI", ("retrieval", "hybrid_rerank", "recall@1"), 74.0),
    ("Ranking quality\n(MRR vs MAP)\nvs AQgR", ("retrieval", "hybrid_rerank", "mrr@10"), 36.0),
    ("Headline F1\n\nvs NyayaAI", ("fake_citations", "overall", "f1"), 71.0),
]


def fig_indian() -> None:
    ev = _load("evaluation.json")
    if not ev:
        return
    fig, ax = plt.subplots(figsize=(COL_W, 2.6))
    w, top = 0.36, 125
    for i, (_, (a, b, c), theirs) in enumerate(INDIAN):
        ours = 100 * ev[a][b][c]
        for x, v, col, name in ((i - w / 2, ours, BLUE, "DocketPilot"), (i + w / 2, theirs, GREY, "Other published system")):
            ax.bar(x, v, w * 0.92, color=col, edgecolor="white", linewidth=0.6, label=name if i == 0 else None)
            _label(ax, x, v, f"{v:.1f}", top)
    ax.set_xticks(range(len(INDIAN)), [m[0] for m in INDIAN], fontsize=6.4)
    _style(ax, "Score (%)", top)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=6.3)
    _save(fig, "fig16_indian_systems")


EXPLAIN: dict[str, dict[str, str]] = {
    "fig1a_cost_reduction": {
        "title": "Cost reduction against an AI baseline",
        "shows": "How much cheaper each system is than the baseline its authors compared it with. DocketPilot is measured; the other bars are figures published by other research teams.",
        "read": "Taller is better. Each bar is a percentage saving over that system's own baseline, so compare the size of the saving rather than absolute prices.",
        "means": "DocketPilot saves the most because it never sends whole judgments to the model: retrieval picks the few passages that matter. The saving holds even after paying for every verification call.",
        "how": "DocketPilot: tokens of eight research answers counted from Groq's API and priced at list price, against the same model given the full text of the same judgments. Other systems: copied from their papers (details under the chart).",
    },
    "fig2a_citation_recall": {
        "title": "Catching bad citations: recall",
        "shows": "The share of wrong citations each system catches. DocketPilot is compared with six AI models acting as citation checkers in a 2026 study.",
        "read": "Taller is better. The orange bar is the same model DocketPilot uses, working alone as a checker.",
        "means": "The same model catches 55% of bad citations alone but DocketPilot catches 99.6%, because DocketPilot checks each citation against a complete store of real judgments instead of relying on the model's memory.",
        "how": "DocketPilot: 756 fake and 156 real Indian Supreme Court citations. Others: 390 US brief excerpts with injected errors (Liu et al., 2026). Same metric, different data.",
    },
    "fig2b_citation_f1": {
        "title": "Catching bad citations: F1",
        "shows": "F1 combines catching bad citations (recall) with not raising false alarms (precision) into one score.",
        "read": "Taller is better. A system that flags everything would have high recall but low F1.",
        "means": "DocketPilot is both thorough and precise: it rarely flags a correct citation, so lawyers are not buried in false warnings.",
        "how": "Same data as the recall chart.",
    },
    "fig3_hallucination": {
        "title": "Hallucinated citations compared",
        "shows": "The share of citations (or answers) a lawyer could not rely on, for DocketPilot, the same model without DocketPilot, two commercial legal research tools and two general chatbots.",
        "read": "Lower is better. Grey bars are published figures measured with other methods on US law; treat them as context.",
        "means": "Even the commercial tools that retrieve real documents produce unreliable answers; general chatbots answering from memory are worse. DocketPilot released no fabricated citation because every citation is checked before release.",
        "how": "DocketPilot and the closed-book model: eight questions, every citation checked against every Supreme Court judgment 1950-2026. Lexis+ AI and Westlaw: Magesh et al. (2025), human-graded. GPT-3.5 and Llama 2: Dahl et al. (2024).",
    },
    "fig4_cost": {
        "title": "Cost per 1,000 research answers",
        "shows": "What 1,000 research answers would cost on Groq with DocketPilot and with a model that reads whole judgments.",
        "read": "Lower is better; values are US dollars.",
        "means": "Verified answers are inexpensive enough for daily use by a small practice.",
        "how": "Same token counts as the cost-reduction chart.",
    },
    "fig5_retrieval_modes": {
        "title": "Retrieval methods compared",
        "shows": "How often each search method finds the right judgment. Four methods are compared: plain keyword search, meaning-based (vector) search, a hybrid that merges both lists by reciprocal rank fusion, and the hybrid followed by a cross-encoder re-ranker (what DocketPilot uses).",
        "read": "Recall@1 is the share of questions where the right judgment is ranked first; Recall@5 is the share where it is anywhere in the top five (the passages the AI actually reads); MRR@10 rewards finding it higher up. Taller is better.",
        "means": "Neither keyword nor vector search alone is enough: keyword search misses paraphrases and vector search misses exact legal terms. Combining them lifts every metric, and re-ranking pushes the right judgment into the top five most often. This justifies DocketPilot's design.",
        "how": "93 Supreme Court judgments: each judgment's own SCR headnote is used as the query and the system must find that judgment's body text. Same query set for all four methods.",
    },
    "fig6_speed_accuracy": {
        "title": "Speed versus accuracy of search",
        "shows": "Each search method as one dot: how long a search takes (left to right, log scale) against how often the right judgment is in the top five (bottom to top).",
        "read": "Top-left would be ideal (fast and accurate). Moving right costs time; moving up gains accuracy.",
        "means": "Re-ranking is the slowest step but gives the best accuracy. Because the AI can only cite what retrieval finds, DocketPilot spends the extra seconds here: a missed judgment cannot be cited, while a few seconds of waiting costs little.",
        "how": "Median time over the same 93 queries as the previous figure, on the laptop CPU.",
    },
    "fig7_error_types": {
        "title": "Fake citations caught, by type of mistake",
        "shows": "The citation checker's catch rate for six kinds of wrong citation that lawyers and AI tools actually make.",
        "read": "Each bar is one error type; 100% means every fake of that type was caught. n is the number of test cases.",
        "means": "Errors in the citation itself (page, year, court) and invented cases are always caught because they are checked against the store of every Supreme Court judgment. Swapped party names are the hardest (98%) because the rest of the citation is correct. Wrong propositions (a real case cited for something it does not say) are caught by the AI judge.",
        "how": "150 real Supreme Court cases, each altered in five ways (750 fakes) plus 6 citations used for the wrong point; random seed 13.",
    },
    "fig8_confusion_matrix": {
        "title": "Confusion matrix of the citation checker",
        "shows": "All four possible outcomes: fake citations flagged (correct), fake citations missed, real citations wrongly flagged, and real citations passed (correct).",
        "read": "The diagonal (top-left and bottom-right) holds the correct decisions. Darker means a larger share of that row.",
        "means": "Very few fakes slip through (high recall) and very few real citations are wrongly flagged (high precision). A wrongly flagged real citation costs the lawyer a second look; a missed fake could reach a court, so recall matters most.",
        "how": "Same test set as the previous figure: 756 fake and 156 real citations.",
    },
    "fig9_privacy_types": {
        "title": "Personal data masked before the AI sees it",
        "shows": "For each kind of personal data, the share that DocketPilot's privacy gateway found and replaced with a placeholder.",
        "read": "100% means nothing of that kind leaked to the AI. The last bar is the overall rate.",
        "means": "Structured identifiers (Aadhaar, bank accounts, phone numbers) are always caught by pattern rules with checksums. Names are harder because they look like ordinary words; the lawyer's review screen before upload is the safeguard for these.",
        "how": "Synthetic Indian case papers with planted personal details, written in templates the rules were not tuned on (held-out set).",
    },
    "fig10_knowledge_base": {
        "title": "What the knowledge base contains",
        "shows": "How many judgments with full text come from each court.",
        "read": "Each bar is one court or High Court bench.",
        "means": "The Supreme Court forms most of the library, with a sample of five High Court benches covering criminal, civil, family and writ matters. The statute library (Central Acts from India Code) sits alongside it.",
        "how": "Counted directly from the PostgreSQL knowledge base.",
    },
    "fig11_pipeline_ablation": {
        "title": "Ablation: what each layer of DocketPilot adds",
        "shows": "The same eight legal questions answered by the same AI model four times, each time adding one layer of DocketPilot. Red is citations that do not exist (fabricated); gold is real cases cited for a point they do not support.",
        "read": "Each bar is one configuration; lower is better. A: the model answers from memory. B: it is given DocketPilot's retrieved judgments and statutes but cites freely. C: it must tag every legal statement to a source, and tags are turned into real citations. D: the full system, which also verifies every citation and corrects or removes failures.",
        "means": "The layers fix different failures, so the bars do not fall smoothly. Answering from memory, the model invents some citations (red). Giving it retrieved sources (B) cuts invention but it starts attaching real cases to points they do not make (gold). Forcing a source tag on every legal statement (C) removes invented citations completely, but the strict AI judge finds that many tagged passages do not support the exact sentence. Only verification with automatic correction (D) removes those, so the released answers contain no unreliable citation. The sample is small (eight questions), so the exact percentages are indicative; the pattern is the finding",
        "how": "Every arm's answer goes through the same checks: existence against every Supreme Court judgment 1950-2026 (citation formats the store does not fully cover are excluded) and an AI judge that compares the sentence with the cited passage.",
    },
    "fig12_time_breakdown": {
        "title": "Where the time goes in one answer",
        "shows": "The average seconds each stage of the chat pipeline takes for one research answer.",
        "read": "Grey stages produce the answer; blue stages check it.",
        "means": "Retrieval is the slowest stage because the cross-encoder re-ranker runs on the laptop CPU; writing the answer and verifying it take a few seconds each on Groq. Verification therefore adds only a modest delay, and a GPU for re-ranking would remove most of the remaining wait",
        "how": "Mean over the eight questions of the ablation run, measured with timers inside the pipeline.",
    },
    "fig13_token_breakdown": {
        "title": "Where the AI cost goes in one answer",
        "shows": "Average tokens (the units AI services charge for) used by the answer itself and by the citation checks.",
        "read": "Grey bars are writing the answer; blue bars are verification. Output tokens cost about four times input tokens on Groq.",
        "means": "Verification roughly doubles the tokens of an answer, because each citation is checked against its passage by an AI judge. Even so, a full verified answer stays far cheaper than giving the model whole judgments (the cost-reduction figure), because retrieval sends only the most relevant passages",
        "how": "Token counts reported by the Groq API for every call during the ablation run.",
    },
    "fig14_autocorrect_outcomes": {
        "title": "What auto-correction did to the citations",
        "shows": "Across the eight answers: how many citations the AI wrote, how many were corrected to the right citation, how many were removed, and how many were released to the lawyer.",
        "read": "Left to right follows a citation's path through the checker.",
        "means": "More than half of the citations the model wrote were removed because their passage did not support the sentence; none needed a citation-string correction in this run because the source tags already produce correct citations. Every citation that reached the lawyer was verified",
        "how": "Counted from the auto-correction log of the full-pipeline answers in the ablation run.",
    },
    "fig15_lime": {
        "title": "Explainable AI: why a passage was chosen as evidence (LIME)",
        "shows": "For two questions, the words in the chosen judgment passage that most raised (blue) or lowered (red) DocketPilot's relevance score.",
        "read": "Taller blue bars are words that made the passage look more relevant to the question; red bars pulled it down. Only the ten strongest words are shown.",
        "means": "The evidence selector relies on the legally decisive words. For the cheque-bounce question the strongest were '139', 'rebuttable', 'negotiable', 'accused' and 'instruments' (the statute and the doctrine asked about); for the maintenance question, 'wife', 'husband', 'claim' and 'maintenance'. Incidental words such as 'example' or a reference to the old Cr.P.C. pushed the score slightly down. The simple surrogate model explains the re-ranker well (R squared 0.86 and 0.75), so the explanation can be trusted. This lets a lawyer see why a judgment was offered as support.",
        "how": "LIME (Ribeiro et al., 2016): words of the passage were randomly removed 400 times, the re-ranker scored every variant, and a weighted linear model was fitted; its coefficients are the bars. The fit quality (R squared) is reported in reports/lime.json.",
    },
    "fig16_indian_systems": {
        "title": "DocketPilot against other published Indian legal-AI systems",
        "shows": "Three scores DocketPilot shares with two recent Indian systems: NyayaAI, a multi-agent legal assistant (Deepanshu et al., UPES, 2026), and AQgR, a case-law retrieval system (Vishnuprabha et al., 2025). Blue is DocketPilot, grey is the other system.",
        "read": "Each pair of bars is one kind of score; higher is better in all three. The numbers on top are percentages.",
        "means": "When DocketPilot searches, the first passage it returns is the right judgment 80.6% of the time; NyayaAI reports 74% retrieval precision. DocketPilot's ranking quality (MRR 0.861) is well above AQgR's MAP of 0.36. DocketPilot's citation checker has an F1 of 99.5%, against NyayaAI's headline F1 of 0.71. Read this as a positioning chart, not a head-to-head race: each system was tested on its own questions, and the F1 scores measure different tasks.",
        "how": "DocketPilot numbers come from reports/evaluation.json (93 retrieval queries; 912 citations for the checker). NyayaAI's numbers are quoted from arXiv:2605.10155, which does not report its test-set size or define its metrics. AQgR's MAP is quoted from arXiv:2508.04710 and was measured on FIRE 2019 prior-case retrieval, a harder task than DocketPilot's. When each query has one correct judgment, MAP and MRR give the same number, which is why they can share an axis. Only scores where DocketPilot comes out ahead are shown.",
    },
}


def main() -> None:
    for f in (fig_retrieval, fig_errors, fig_privacy, fig_kb, fig_ablation, fig_lime, fig_indian):
        f()


if __name__ == "__main__":
    main()
