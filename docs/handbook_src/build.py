# ruff: noqa: E501  (embedded CSS lines)
"""Build docs/DocketPilot_Handbook.html: one shareable file, images embedded.

Part A (understanding.html): folders, files, Docker, storage, examiner questions. Part B (research.html): workflow,
agents, benchmarks, comparison, figures. Method notes under each figure come from docketpilot/evaluation/figures.py.

    .venv-gpu\\Scripts\\python docs\\handbook_src\\build.py      (needs Pillow; run figures.py first if numbers changed)
"""
import base64
import html
import io
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from docketpilot.evaluation.figures import METHODS  # noqa: E402

PART_A = ["minute", "layers", "storage", "docker", "root", "code", "other", "db", "journeys", "tools", "qa", "words"]
PART_B = ["workflow", "agents", "chat", "retrieval", "verify", "privacy", "stack", "ui", "data", "bench", "compare", "figs", "run",
          "limits", "refs"]
SHOTS = [("s0_home", "Home page", "The public home page in court green and white: a hero with the product promise over a DocketPilot draft, then how it works, everyday matters, a product overview, measured results and a call to action."),
         ("s1_signin", "Sign in", "Sign in and Create account open in a panel over the home page; e-mail accounts and Google sign-in are both supported."),
         ("s7_dashboard", "Dashboard", "Greeting, four quick actions, three headline numbers, a timeline of coming dates, drafts waiting for review and recent cases."),
         ("s2_masking_review", "Masking review in the chat", "After a paper is dropped in, every identifier is listed with the placeholder that replaces it. The lawyer can untick or add items, then files it."),
         ("s3_verified_answer", "Verified research answer", "Citations are underlined; hovering one previews its passage, clicking pins it in the Source panel. The green line says how many references were checked and removed."),
         ("s6b_draft_progress", "Draft in progress", "A live stepper shows which of the seven agents has finished."),
         ("s6_draft_verification", "Draft review", "The draft on ruled legal paper with colour-coded citations, the evidence panel, the sign-off card and tabs for checks, the checklist and precedent."),
         ("s4_calendar", "Calendar", "Month grid colour-coded by kind of date; the details panel shows the sentence each date came from."),
         ("s5_find_section", "Find a section", "Central Acts searched by topic; each result opens to the section text from India Code."),
         ("s8_dashboard_dark", "Dark mode", "The same dashboard in the dark theme (toggle in the top bar; remembered per device)."),
         ("s9_mobile_chat", "Phone layout", "The chat on a 390-pixel-wide phone screen; the menu becomes a slide-out drawer.")]

EXTRA_CSS = """
.explain{border-left:4px solid #2a6fc0;background:var(--code);padding:8px 14px 2px;margin:4px 0 10px;font-size:13.5px}.explain ul{margin:0;padding-left:18px}.explain li{margin-bottom:6px;max-width:none}
.part{border-top:0;margin-top:56px}.partlabel{font:700 24px var(--display);color:var(--seal);letter-spacing:.04em;border-bottom:3px double var(--seal);padding-bottom:6px;margin-bottom:6px}
.navpart{margin:14px 0 4px;font:600 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:#f2c56b}
.where{border-left:4px solid var(--gold);background:var(--gold-soft);padding:10px 14px;margin:12px 0;color:var(--ink)}
.plain{border-left:4px solid #2a6fc0;background:var(--code);padding:10px 14px;margin:12px 0;color:var(--ink)}
.folder{border:1px solid var(--rule);margin:18px 0;padding:14px 16px;background:var(--page)}
.folder h3{margin:0 0 4px;font:600 16px var(--mono)} .folder .what{margin:0 0 8px;color:var(--ink)}
.folder td:first-child,#storage td:first-child,#docker td:first-child,#root td:first-child,#other td:first-child,#db td:first-child{white-space:nowrap}
.layers{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin:14px 0}
.layer{border:1px solid var(--rule);border-top:3px solid var(--gold);padding:10px 12px}.layer b{display:block}.layer span{font-size:13px;color:var(--mute)}
.steps{counter-reset:s;list-style:none;padding:0}.steps li{counter-increment:s;position:relative;padding:6px 0 6px 38px;border-bottom:1px dashed var(--rule)}
.steps li::before{content:counter(s);position:absolute;left:0;top:7px;width:26px;height:26px;border-radius:50%;background:var(--spine);color:#fff;font:600 13px/26px var(--sans);text-align:center}
details.qa{border:1px solid var(--rule);margin:8px 0;padding:8px 12px;background:var(--page)}details.qa summary{cursor:pointer;font-weight:600;color:var(--ink)}details.qa p{margin:8px 0 2px}
@media (max-width:860px){.folder td:first-child,#storage td:first-child,#docker td:first-child,#root td:first-child,#other td:first-child,#db td:first-child{white-space:normal}}
</style>"""


def _sections(main: str) -> dict[str, str]:
    return {re.search(r'id="(\w+)"', s).group(1): s for s in re.findall(r'<section id="\w+">.*?</section>', main, re.S)}


def _uri(path: Path, width: int) -> str:
    im = Image.open(path).convert("RGBA" if path.name == "logo.png" else "RGB")
    if im.width > width:
        im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _method(name: str) -> str:
    items = "".join(f"<li><b>{html.escape(w)}</b>: {html.escape(h)}</li>" for w, h in METHODS.get(name, []))
    return f'\n  <div class="method"><b class="mh">How this comparison was made</b><ul>{items}</ul></div>'


FIG_ORDER = ["fig11_pipeline_ablation", "fig3_hallucination", "fig2a_citation_recall", "fig2b_citation_f1", "fig1a_cost_reduction",
             "fig4_cost", "fig5_retrieval_modes", "fig6_speed_accuracy", "fig7_error_types", "fig8_confusion_matrix",
             "fig9_privacy_types", "fig10_knowledge_base", "fig12_time_breakdown", "fig13_token_breakdown",
             "fig14_autocorrect_outcomes", "fig15_lime", "fig16_indian_systems"]


def _figures_section() -> str:
    """Every chart, each with what it shows / how to read it / what it means / how it was measured."""
    from docketpilot.evaluation.figures_extra import EXPLAIN

    parts = ['<section id="figs"><h2>Figures for the paper</h2>',
             '<p>All charts are in <span class="path">reports/figures/</span> as 600 dpi PNG and SVG, sized for one IEEE column. '
             'Under each chart: what it shows, how to read it, what it means, and how it was measured, so you can explain it to anyone.</p>']
    for i, name in enumerate([n for n in FIG_ORDER if (ROOT / "reports" / "figures" / f"{n}.png").exists()], 1):
        e = EXPLAIN.get(name, {})
        parts.append(f'<h3>Figure {i}. {html.escape(e.get("title", name))}</h3>')
        parts.append(f'<figure class="fig"><img src="{{{{F:{name}}}}}" alt="{html.escape(e.get("title", name))}">'
                     f'<figcaption>{name}.png</figcaption></figure>')
        rows = "".join(f"<li><b>{label}</b>: {html.escape(e[k])}</li>" for k, label in
                       (("shows", "What it shows"), ("read", "How to read it"), ("means", "What it means"), ("how", "How it was measured"))
                       if k in e)
        parts.append(f'<div class="explain"><ul>{rows}</ul></div>')
        if name in METHODS:
            parts.append(_method(name))
    parts.append("</section>")
    return "\n".join(parts)


def _ui_section() -> str:
    """Screens of the React interface and the automated usability check."""
    import json

    parts = ['<section id="ui"><h2>The interface</h2>',
             '<p>The screen is a React 18 + TypeScript app (<span class="path">frontend/</span>) with Tailwind CSS, Radix UI components, '
             'a Ctrl+K command palette, light and dark themes and a phone layout. It calls the same API as before, so the AI pipeline is unchanged. '
             'Screens below were captured from the running system with a synthetic case paper.</p>']
    for name, title, text in SHOTS:
        p = ROOT / "reports" / "screenshots" / f"{name}.png"
        if p.exists():
            parts.append(f'<h3>{html.escape(title)}</h3><figure class="fig"><img src="{{{{S:{name}}}}}" alt="{html.escape(title)}">'
                         f'<figcaption>{html.escape(text)}</figcaption></figure>')
    rp = ROOT / "reports" / "ui_usability.json"
    if rp.exists():
        r = json.loads(rp.read_text(encoding="utf-8"))
        tasks = r.get("tasks", [])
        ok = sum(t["success"] for t in tasks)
        rows = "".join(f'<tr><td>{html.escape(t["task"])}</td><td class="n">{"✓" if t["success"] else "✕"}</td>'
                       f'<td class="n">{t["user_actions"]}</td><td class="n">{t["seconds"]:.1f} s</td></tr>' for t in tasks)
        axe = r.get("axe", {})
        detail = {pg: ", ".join("{} ({}, {})".format(x["id"], x["impact"], x["nodes"]) for x in v) or "none" for pg, v in axe.items()}
        arow = "".join(f'<tr><td>{html.escape(pg)}</td><td class="n">{len(v)}</td><td>{html.escape(detail[pg])}</td></tr>' for pg, v in axe.items())
        resp = r.get("responsive", {})
        phone = [k.split("@")[0] for k, v in resp.items() if k.endswith("@390") and not v["ok"]]
        sp = r.get("speed", {})
        parts.append(f'<h3>Usability check</h3><p><b>{ok} of {len(tasks)}</b> tasks completed. "Actions" counts the clicks, key presses and '
                     'typed fields a person needs; times measure the interface only (no AI call).</p>'
                     f'<div class="tbl"><table><thead><tr><th>Task</th><th>Done</th><th>Actions</th><th>Time</th></tr></thead><tbody>{rows}</tbody></table></div>'
                     '<p>Accessibility: axe-core with the WCAG 2.1 A and AA rules on every page (rule, impact, number of elements).</p>'
                     f'<div class="tbl"><table><thead><tr><th>Page</th><th>Rules failed</th><th>Details</th></tr></thead><tbody>{arow}</tbody></table></div>'
                     f'<p>Phone width (390 px): {"no page scrolls sideways" if not phone else "sideways scrolling on " + ", ".join(phone)}. '
                     f'Reload to an interactive dashboard: {sp.get("reload_to_interactive_dashboard_s", "?")} s on the laptop.</p>'
                     '<div class="method"><b class="mh">How this check was made</b><ul>'
                     '<li><b>Script</b>: tools/ui_usability_test.py drives Microsoft Edge (headless) through the Chrome DevTools Protocol on a fresh account with the synthetic case paper.</li>'
                     '<li><b>Success</b>: each task passes only if the expected result appears on screen within 25 seconds.</li>'
                     '<li><b>Limits</b>: this is an automated check, not a study with real lawyers. A study with practising advocates (task time, errors, '
                     'System Usability Scale) is planned.</li></ul></div>')
    parts.append("</section>")
    return "\n".join(parts)


def main() -> None:
    hb = (SRC / "research.html").read_text(encoding="utf-8")
    gd = (SRC / "understanding.html").read_text(encoding="utf-8")
    inner = lambda s: s[s.index("<main>") + 6:s.index("</main>")]  # noqa: E731
    H, G = _sections(inner(hb)), _sections(inner(gd))
    G["minute"] = re.sub(r'<h1>.*?</h1>\s*<p style="color:var\(--gold\);font-style:italic">.*?</p>',
                         "<h2>The project in one minute</h2>", G["minute"], flags=re.S)
    for i, k in enumerate(PART_A, 1):
        G[k] = re.sub(r"<h2>(?:\d+\.\s*)?(.*?)</h2>", lambda m, i=i: f"<h2>A{i}. {m.group(1)}</h2>", G[k], count=1)
    H["figs"] = _figures_section()
    H["ui"] = _ui_section()
    for i, k in enumerate(PART_B, 1):
        H[k] = re.sub(r"<h2>(.*?)</h2>", lambda m, i=i: f"<h2>B{i}. {m.group(1)}</h2>", H[k], count=1)
    part = lambda t, sub: f'<section class="part"><div class="partlabel">{t}</div><p>{sub}</p></section>'  # noqa: E731
    body = (H["overview"]
            + part("Part A · Understanding the project", "What every folder and file is for, Docker and where all data "
                   "is stored, and answers to examiner questions. Written for beginners.")
            + "".join(G[k] for k in PART_A)
            + part("Part B · Research and benchmarks", "How DocketPilot works in detail, the measured results, the "
                   "comparison with other systems, and the figures for the paper.")
            + "".join(H[k] for k in PART_B))
    body = re.sub(r'(<figure class="fig"><img src="\{\{F:(\w+)\}\}"[^\n]*?</figure>)',
                  lambda m: m.group(1) + (_method(m.group(2)) if m.group(2) != "SLIDE" else ""), body)
    title = lambda d, k: re.sub("<[^>]+>", "", re.search(r"<h2>(.*?)</h2>", d[k], re.S).group(1))  # noqa: E731
    nav = ('<a href="#overview">Introduction</a><div class="navpart">Part A · Understanding</div>'
           + "".join(f'<a href="#{k}">{title(G, k)}</a>' for k in PART_A)
           + '<div class="navpart">Part B · Research</div>'
           + "".join(f'<a href="#{k}">{title(H, k)}</a>' for k in PART_B))
    head = hb[:hb.index("<main>")]
    head = re.sub(r'<div class="links">.*?</div>\s*</nav>', f'<div class="links">{nav}</div>\n</nav>', head, flags=re.S)
    head = head.replace("Research handbook · 28 Oct 2026", "Handbook · understanding + research")
    head = head.replace("<title>DocketPilot Research Handbook</title>", "<title>DocketPilot Handbook</title>")
    head = head.replace("</style>", EXTRA_CSS, 1)
    page = head + "<main>\n" + body + "\n" + hb[hb.index("</main>"):]
    page = page.replace("{{LOGO}}", _uri(ROOT / "docketpilot" / "web" / "logo.png", 160))
    page = page.replace("{{F:SLIDE}}", _uri(ROOT / "docs" / "diagrams" / "workflow_slide.png", 1800))
    page = re.sub(r"\{\{F:(\w+)\}\}", lambda m: _uri(ROOT / "reports" / "figures" / f"{m.group(1)}.png", 1000), page)
    page = re.sub(r"\{\{S:(\w+)\}\}", lambda m: _uri(ROOT / "reports" / "screenshots" / f"{m.group(1)}.png", 1400), page)
    out = ROOT / "docs" / "DocketPilot_Handbook.html"
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(page) // 1024} KB, {page.count('<section')} sections)")


if __name__ == "__main__":
    main()
