"""Block diagram of DocketPilot for the project report -> docs/report/block_diagram.png, plus a rotated workflow page.

    .venv-gpu\\Scripts\\python docs\\report\\make_block_diagram.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INK, EDGE, MUTE = "#1f2328", "#3d4148", "#5a5f67"
FILL = {"user": "#fdf1e7", "api": "#e8f0f8", "graph": "#e3f1ec", "data": "#f6f0e1", "out": "#eef3e5"}
LANE = {"user": "#c8501e", "api": "#2a6fc0", "graph": "#1b6b52", "data": "#9a7414", "out": "#5d7a2a"}
X0, X1 = 7.0, 62.0  # usable width for boxes (figure units: 0.1 inch)


def box(ax, x, y, w, h, title, sub, kind):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.8",
                                facecolor=FILL[kind], edgecolor=EDGE, linewidth=1.0))
    if sub:
        ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center", fontsize=8.3, fontweight="bold", color=INK)
        ax.text(x + w / 2, y + h * 0.3, sub, ha="center", va="center", fontsize=6.4, color=MUTE, linespacing=1.15)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=7.4, color=INK)


def row(ax, y, h, items, kind):
    """Boxes of equal width across the usable width; returns their (x, w)."""
    gap = 1.2
    w = (X1 - X0 - gap * (len(items) - 1)) / len(items)
    out = []
    for i, (t, s) in enumerate(items):
        x = X0 + i * (w + gap)
        box(ax, x, y, w, h, t, s, kind)
        out.append((x, w))
    return out


def arrow(ax, p, q, text=None, dx=0.6):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=9, color=EDGE, linewidth=0.9, shrinkA=0, shrinkB=0))
    if text:
        ax.text((p[0] + q[0]) / 2 + dx, (p[1] + q[1]) / 2, text, fontsize=6.2, color=MUTE, va="center", style="italic")


def lane(ax, y0, y1, label, kind):
    ax.add_patch(FancyBboxPatch((1, y0), 62, y1 - y0, boxstyle="round,pad=0,rounding_size=0.6",
                                facecolor="#fbfbfa", edgecolor="#d5d8dc", linewidth=0.7))
    ax.add_patch(FancyBboxPatch((1, y0), 4.6, y1 - y0, boxstyle="round,pad=0,rounding_size=0.6",
                                facecolor=LANE[kind], edgecolor="none"))
    ax.text(3.3, (y0 + y1) / 2, label, rotation=90, ha="center", va="center", fontsize=7, fontweight="bold", color="white")


def block_diagram() -> None:
    fig = plt.figure(figsize=(6.4, 8.6))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 64)
    ax.set_ylim(0, 86)
    ax.axis("off")

    lane(ax, 75.5, 85, "USER", "user")
    u = row(ax, 77, 6.5, [("Advocate / junior", "uploads papers · asks · approves"),
                          ("Web interface", "chat · masking review · drafts\ncalendar · dashboard")], "user")

    lane(ax, 57, 74.5, "BACKEND", "api")
    b1 = row(ax, 66.5, 6, [("Auth and audit", "JWT · roles · firm isolation"),
                           ("Privacy gateway", "rules + NER → PERSON_1\nreal names to vault"),
                           ("Chat router", "rule-based intent\nselection")], "api")
    row(ax, 58.5, 6, [("Research and verify tools", "verified answer · similar cases\nverify pasted text"),
                      ("Case files and calendar", "matters · dates with quotes\nreminders · dashboard")], "api")

    lane(ax, 31.5, 56, "AGENT GRAPH (LangGraph)", "graph")
    r1 = row(ax, 47.5, 6, [("1 Orchestrator", "plans the run"), ("2 Doc analysis", "facts + quotes"),
                           ("3 Research", "law + precedent"), ("4 Drafting", "source-tagged")], "graph")
    r2 = row(ax, 39.5, 6, [("Lawyer approval", "interrupt · edit"), ("7 Monitoring", "deadlines"),
                           ("6 Strategy, risk", "checklist · cases"), ("5 Verification", "check + repair")], "graph")
    row(ax, 33, 4.5, [("Finalize: restore real names from the vault · Word document · calendar entries", "")], "out")
    for a, c in zip(r1[:-1], r1[1:], strict=False):
        arrow(ax, (a[0] + a[1], 50.5), (c[0], 50.5))
    for a, c in zip(r2[1:], r2[:-1], strict=False):
        arrow(ax, (a[0], 42.5), (c[0] + c[1], 42.5))
    arrow(ax, (r1[3][0] + r1[3][1] / 2, 47.5), (r2[3][0] + r2[3][1] / 2, 45.5))
    arrow(ax, (r2[0][0] + r2[0][1] / 2, 39.5), (r2[0][0] + r2[0][1] / 2, 37.5))

    lane(ax, 13.5, 30.5, "RETRIEVAL · MODEL · CHECKS", "data")
    m = row(ax, 22.5, 6.5, [("Tiered retrieval", "exact cite · statute on date\nkeyword · vectors · re-rank"),
                            ("LLM: gpt-oss-120b", "Groq · masked text only\nunder 8k tokens a request"),
                            ("Verification engine", "resolve · quote · AI judge\ngood law · in force")], "data")
    gx = m[1][0]
    box(ax, gx, 15, X1 - gx, 5.5, "Automatic correction and release gate",
        "fix wrong citation strings · remove unsupported claims\nverified / acknowledge / blocked", "out")
    for a, c in zip(m[:-1], m[1:], strict=False):
        arrow(ax, (a[0] + a[1], 25.75), (c[0], 25.75))
    arrow(ax, (m[2][0] + m[2][1] / 2, 22.5), (m[2][0] + m[2][1] / 2, 20.5))

    lane(ax, 1, 12.5, "DATA", "data")
    d = row(ax, 6, 5.5, [("PostgreSQL 16", "cases · passages · statutes\ncase files · audit · checkpoints"),
                         ("Qdrant", "dense vectors\nbge-small-en-v1.5"),
                         ("Encrypted vault", "placeholder → real name\nFernet, per case file")], "data")
    row(ax, 2, 3.2, [("Offline build: Supreme Court and High Court judgments (CC-BY-4.0) · India Code Acts and sections", "")], "data")

    # flows between lanes
    arrow(ax, (u[1][0] + 8, 77), (b1[1][0] + b1[1][1] / 2, 72.5), "masked text")
    arrow(ax, (b1[2][0] + b1[2][1] / 2, 66.5), (b1[2][0] + b1[2][1] / 2, 64.5))
    arrow(ax, (34.5, 58.5), (34.5, 53.5), "draft request")
    arrow(ax, (34.5, 33), (34.5, 29), "retrieve · generate · verify")
    arrow(ax, (d[0][0] + d[0][1] / 2, 11.5), (m[0][0] + m[0][1] / 2, 22.5))
    arrow(ax, (d[1][0] + 1.5, 11.5), (m[0][0] + m[0][1] * 0.8, 22.5))
    fig.savefig(HERE / "block_diagram.png", dpi=300, facecolor="white")
    plt.close(fig)
    print("wrote", HERE / "block_diagram.png")


def workflow_page() -> None:
    im = Image.open(ROOT / "docs" / "diagrams" / "workflow.png").convert("RGB")
    im = im.crop((0, 0, im.width, int(im.height * 0.918)))  # drop the legend strip at the bottom
    im.rotate(90, expand=True).save(HERE / "workflow_rotated.png", optimize=True)
    print("wrote", HERE / "workflow_rotated.png")


if __name__ == "__main__":
    block_diagram()
    workflow_page()
