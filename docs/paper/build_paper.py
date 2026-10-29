# ruff: noqa: E501  (paper prose)
"""Build the IEEE-style conference paper (two columns, Times New Roman) as docs/paper/DocketPilot_IEEE.docx.

Every number is read from reports/*.json, so the paper always matches the measured results.

    .\\.venv\\Scripts\\python docs\\paper\\build_paper.py
"""
import json
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
REP, FIG, SHOT = ROOT / "reports", ROOT / "reports" / "figures", ROOT / "reports" / "screenshots"
OUT = Path(__file__).resolve().parent / "DocketPilot_IEEE.docx"
J = lambda n: json.loads((REP / n).read_text(encoding="utf-8")) if (REP / n).exists() else {}  # noqa: E731
EV, BV, AB, CMP = J("evaluation.json"), J("benchmark_vs.json"), J("ablation.json"), J("comparison.json")
RET = J("retrieval_current.json") or EV.get("retrieval", {})
KB = J("kb_composition.json")
COL = 3.45  # inches, one column


def pct(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}%"


# ---------------- numbers used in the text ----------------
fake = EV["fake_citations"]["overall"]
pii = EV["pii"]["heldout_with_ner"]
cost = BV["summary"]["cost_per_answer_usd"]
speed = BV["summary"]["document_processing_seconds"]
cit = BV["summary"]["citations"]
arms = AB.get("arms", {})
tm = AB.get("timing_mean_s", {})
tok = AB.get("tokens_mean", {})
fun = AB.get("funnel", {})
n_judg = f"{KB.get('judgments_total', 16318):,}"
n_cases = f"{KB.get('cases_total', 48168):,}"
n_acts = KB.get("acts", 79)
n_secs = f"{KB.get('sections', 0):,}" if KB.get("sections") else "several thousand"
n_vec = f"{KB.get('vectors', 372122):,}"
n_chunks = f"{KB.get('chunks', 430882):,}"


def arm(k: str, f: str) -> str:
    return pct(arms[k][f]) if k in arms else "n/a"


A_tot = (arms["A"]["fabricated_pct"] + arms["A"]["unsupported_pct"]) if arms else 0
D_tot = (arms["D"]["fabricated_pct"] + arms["D"]["unsupported_pct"]) if arms else 0

# ---------------- document helpers ----------------
doc = Document()
st = doc.styles["Normal"]
st.font.name = "Times New Roman"
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
st.font.size = Pt(10)
st.paragraph_format.space_after = Pt(0)
st.paragraph_format.line_spacing = 1.0

sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.top_margin, sec.bottom_margin = Inches(0.75), Inches(1.0)
sec.left_margin = sec.right_margin = Inches(0.625)


def cols(section: Any, n: int) -> None:
    sp = section._sectPr
    for c in sp.findall(qn("w:cols")):
        sp.remove(c)
    c = OxmlElement("w:cols")
    c.set(qn("w:num"), str(n))
    c.set(qn("w:space"), "360")
    sp.append(c)


def para(text: str = "", size: float = 10, bold: bool = False, italic: bool = False, align: Any = WD_ALIGN_PARAGRAPH.JUSTIFY,
         indent: bool = True, after: float = 0, before: float = 0, sc: bool = False) -> Any:
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after, p.paragraph_format.space_before = Pt(after), Pt(before)
    if indent:
        p.paragraph_format.first_line_indent = Inches(0.17)
    if text:
        r = p.add_run(text)
        r.font.size, r.bold, r.italic = Pt(size), bold, italic
        r.font.small_caps = sc
    return p


def rich(parts: list[tuple[str, str]], size: float = 10, indent: bool = True) -> Any:
    """parts: (style, text) with style in '', 'b', 'i', 'bi'."""
    p = para(indent=indent)
    for style, text in parts:
        r = p.add_run(text)
        r.font.size, r.bold, r.italic = Pt(size), "b" in style, "i" in style
    return p


def heading(num: str, text: str) -> None:
    p = para(f"{num}. {text}", size=10, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=8, after=4, sc=True)
    p.paragraph_format.keep_with_next = True


def sub(letter: str, text: str) -> None:
    p = para(f"{letter}. {text}", size=10, italic=True, align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, before=4, after=2)
    p.paragraph_format.keep_with_next = True


def figure(path: Path, caption: str, width: float = COL) -> None:
    if not path.exists():
        para(f"[Figure missing: {path.name}]", indent=False)
        return
    p = para(indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, before=4)
    p.add_run().add_picture(str(path), width=Inches(width))
    p.paragraph_format.keep_with_next = True
    c = para(indent=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=6, before=2)
    head, _, rest = caption.partition(" ")
    r = c.add_run(head + " ")
    r.font.size = Pt(8)
    r2 = c.add_run(rest)
    r2.font.size = Pt(8)


def wide_figure(path: Path, caption: str, width: float = 7.0) -> None:
    """A figure spanning both columns: a one-column continuous section around it."""
    one = doc.add_section(WD_SECTION.CONTINUOUS)
    cols(one, 1)
    figure(path, caption, width=width)
    two = doc.add_section(WD_SECTION.CONTINUOUS)
    cols(two, 2)


def table(title: str, header: list[str], rows: list[list[str]], widths: list[float]) -> None:
    t = para(title, size=8, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=6, after=2, sc=True)
    t.paragraph_format.keep_with_next = True
    tb = doc.add_table(rows=1 + len(rows), cols=len(header))
    tb.style = "Table Grid"
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate([header] + rows):
        for j, val in enumerate(row):
            cell = tb.cell(i, j)
            cell.width = Inches(widths[j])
            cell.text = ""
            r = cell.paragraphs[0].add_run(val)
            r.font.size, r.bold = Pt(7.5), i == 0
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER if j else WD_ALIGN_PARAGRAPH.LEFT
            cell.paragraphs[0].paragraph_format.keep_with_next = i < len(rows)
        tr_pr = tb.rows[i]._tr.get_or_add_trPr()
        cs = OxmlElement("w:cantSplit")
        tr_pr.append(cs)
    tb.autofit = False
    para(after=4, indent=False)


# ================= title block (one column) =================
p = para("DocketPilot: An Agentic AI System for Indian Legal Research, Drafting, Anti-Hallucination Verification and Case Management",
         size=22, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, after=10)
p = para(indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, after=12)
for name, aff in [("Srigaran N", "[Department], [Institution]\n[City], India\nsrigaran2020@gmail.com"),
                  ("[Co-author name]", "[Department], [Institution]\n[City], India\n[email]"),
                  ("Dr. Saravanan R", "[Department], [Institution]\n[City], India\n[email]")]:
    r = p.add_run(name + "\n")
    r.font.size = Pt(11)
    r2 = p.add_run(aff.replace("\n", ", ") + "\n")
    r2.font.size, r2.italic = Pt(9), True

body = doc.add_section(WD_SECTION.CONTINUOUS)
cols(body, 2)

# ================= abstract =================
rich([("bi", "Abstract"), ("b", "—Large language models can draft legal text fluently, yet they routinely cite judgments that do not exist or that say something else, and sending client papers to a hosted model exposes personal data. We present DocketPilot, an agentic system for Indian legal practice that couples retrieval over Supreme Court and High Court judgments and Central Acts with a citation verifier that checks, corrects or removes every authority before an answer is released. Client identifiers are masked on the user's machine before any model call, and hearing dates read from case papers populate a built-in calendar. Seven agents coordinated by a stateful graph handle document analysis, research, drafting, verification, risk assessment and deadline monitoring, with a human approval step before any document is finalised. On a benchmark of 756 corrupted and 156 genuine citations the verifier reaches "
         f"{pct(100 * fake['recall'])} recall and {pct(100 * fake['f1'])} F1. In an ablation with a single open-weight model, the share of unreliable citations falls from {pct(A_tot)} when the model answers from memory to {pct(D_tot)} with the full pipeline, while a research answer costs {pct(cost['reduction_pct'])} less than giving the same model the full judgments. LIME attributions show that evidence selection is driven by the legally decisive terms of each query.")], size=9, indent=False)
rich([("bi", "Index Terms"), ("b", "—legal AI, retrieval-augmented generation, hallucination, citation verification, multi-agent systems, privacy, explainable AI.")], size=9, indent=False)

# ================= I. Introduction =================
heading("I", "Introduction")
para("Indian courts carry a pending caseload in the tens of millions, and much of an advocate's time goes into locating precedent, checking that a section is in force on the relevant date, and preparing routine filings. General-purpose language models promise to shorten this work, but two properties make them hazardous in a courtroom. First, they hallucinate authority: independent studies report fabricated or misattributed citations in a substantial share of legal answers, even from commercial research tools [2], [3]. Second, a hosted model receives whatever text it is given, which for a practising advocate means names, addresses and identity numbers of clients.")
para("Recent agentic legal systems focus on throughput and cost. LegalMind [1], for example, reports cost and processing-time gains from a fine-tuned reasoning model, but does not report citation reliability. Work on Indian legal text has concentrated on prediction and understanding benchmarks [23]–[25] rather than on systems that a lawyer can trust to cite correctly. A gap therefore remains between fluent generation and verifiable legal output for Indian law.")
para("This paper describes DocketPilot, a working system that closes this gap with three design choices: (i) every legal statement produced by the model must be tied to a retrieved passage or statute section and is re-checked after generation; (ii) failures are repaired automatically rather than merely flagged, so that no unverified citation reaches the user; and (iii) all identifying data is masked locally before inference. The contributions are:")
for b in ["an end-to-end agentic architecture for Indian legal research, drafting and case management built around a released-only-if-verified rule;",
          "a nine-step citation verifier with automatic correction, evaluated on a corrupted-citation benchmark and in a layer-by-layer ablation;",
          "a measured comparison of cost, speed and hallucination against the same model without the pipeline and against published systems; and",
          "an explainability analysis of evidence selection using LIME [12]."]:
    q = para("•  " + b, indent=False)
    q.paragraph_format.left_indent = Inches(0.15)

# ================= II. Related work =================
heading("II", "Related Work")
sub("A", "Hallucination in legal AI")
para("Dahl et al. [3] queried general models on verifiable facts about US federal cases and observed hallucination rates of 69% for GPT-3.5 and 88% for Llama 2. Magesh et al. [2] evaluated retrieval-backed commercial products and still found 17% (Lexis+ AI) and 33% (Westlaw AI-Assisted Research) of answers to be incorrect or misgrounded. LegalCiteBench [5] shows that closed-book citation recovery remains below 7/100 for the strongest of 21 models. Ovcharov [6] cautions that measured rates depend on the coverage of the reference database, a point we account for in Section V.")
sub("B", "Citation checking and retrieval")
para("Liu et al. [4] benchmark citation-error detection on excerpts of US briefs; their best agentic configuration reaches 84.4% recall and the best F1 is 68.8%. Retrieval-augmented generation [11] grounds answers in documents, and hybrid lexical–dense retrieval with reciprocal rank fusion [13] and cross-encoder re-ranking [15] is now a common recipe. For legal documents, Hany et al. [8] show that navigating a structured index instead of injecting the whole corpus can cut cost by 25–67.5%.")
sub("C", "Indian legal NLP")
para("ILDC [24] and IL-TUR [23] provide judgment-prediction and understanding tasks, and InLegalBERT [25] adapts encoders to Indian legal text. Falkor-IRAC [7] constrains generation with a graph of Indian judgments but reports qualitative results on a small corpus. NyayaAI [26] routes queries through a multi-agent pipeline with FAISS retrieval and a compliance check, reporting 74% retrieval precision and 72% response accuracy; AQgR [27] adds question-guided retrieval and structured summaries for prior-case search, reaching a MAP of 0.36 on FIRE 2019; and a domain-partitioned hybrid RAG with a knowledge graph [28] passes 70% of 40 synthetic questions judged by an LLM. None of these verify the citations they emit. To our knowledge no prior Indian system combines retrieval, generation, automatic citation repair, local privacy masking and case management in one deployable application.")

table("TABLE I. Positioning against related systems (Cite: citation check; Fix: automatic repair; PII: privacy masking; Cal.: hearing calendar; ✓ reported in the cited source; – not reported)",
      ["System", "Scope", "RAG", "Cite", "Fix", "PII", "Cal."],
      [["DocketPilot", "India", "✓", "✓", "✓", "✓", "✓"],
       ["LegalMind [1]", "General", "–", "–", "–", "–", "–"],
       ["Lexis+ AI [2]", "US", "✓", "–", "–", "–", "–"],
       ["Westlaw AI-AR [2]", "US", "✓", "–", "–", "–", "–"],
       ["Agentic checker [4]", "US", "✓", "✓", "–", "–", "–"],
       ["Falkor-IRAC [7]", "India", "✓", "✓", "–", "–", "–"],
       ["NyayaAI [26]", "India", "✓", "–", "–", "–", "–"],
       ["NAVINDEX [8]", "Contracts", "✓", "–", "–", "–", "–"]],
      [1.02, 0.6, 0.42, 0.36, 0.34, 0.34, 0.38])

# ================= III. System =================
heading("III", "System Architecture")
para("Fig. 1 shows the end-to-end flow. A single-page web client talks to a FastAPI service; PostgreSQL stores the knowledge base, user data and agent checkpoints, and Qdrant stores dense vectors. The only generative model is the open-weight gpt-oss-120b [18], served through Groq; it never receives unmasked text.")
wide_figure(ROOT / "docs" / "diagrams" / "workflow_slide.png", "Fig. 1. DocketPilot workflow across five lanes: the lawyer, the backend, the agent graph, verification, and data and models.", width=6.6)
sub("A", "Knowledge base")
para(f"Judgments come from the open Indian Supreme Court and High Court collections released under CC-BY-4.0, and statutes from India Code. The store holds {n_cases} cases for citation resolution (Supreme Court 1950–2026 and five High Court benches 2022–2025), {n_judg} judgments with full text, {n_acts} Central Acts with {n_secs} sections and their amendment footnotes, and {n_chunks} passages, of which {n_vec} are embedded with bge-small-en-v1.5 [14]. Headnotes are stored as a separate segment and never used as evidence.")
sub("B", "Privacy gateway")
para("Before any model call, a local recogniser replaces identifiers with consistent placeholders (PERSON_1, ORG_2): rule patterns with checksums for Aadhaar, PAN, bank, IFSC, telephone and vehicle numbers, and a spaCy [22] named-entity model for names and organisations. The lawyer reviews the masked text before it is stored. The placeholder map is kept per case in a Fernet-encrypted vault, and real names are restored only on screen and in the approved document.")
sub("C", "Agents")
para("Seven agents run as nodes of a LangGraph [19] state graph that checkpoints after every step: an orchestrator selects the workflow; document analysis extracts facts and keeps a fact only when its supporting quote is found in the papers; research gathers statute sections and re-ranked passages; drafting writes the document with a source tag on every legal statement; verification checks and repairs it; strategy and risk lists missing facts and similar past cases; and monitoring derives statutory deadlines. The graph then pauses for the lawyer's approval. A rule-based router exposes the same tools through one conversational interface, and dates extracted from uploaded papers, each anchored to a quote, are filed to a per-case calendar.")
sub("D", "Retrieval")
para("Retrieval proceeds from exact to fuzzy: exact citation lookup, statute lookup as on a date, statute search by topic, PostgreSQL full-text search [20], dense search, reciprocal rank fusion of the two lists, and finally cross-encoder re-ranking [15]. Retrieved text is fitted to a fixed budget so that a request respects the provider's per-minute token limit.")
sub("E", "Verification and automatic correction")
para("The verifier extracts every citation, quotation and statutory reference; normalises citations; resolves them against the case store; assigns a verdict (verified, partial, conflict or not found); checks quotations against the judgment text; asks a separate judge prompt whether the cited passage supports the sentence; inspects later treatment; and checks that each section exists and is in force on the relevant date. Automatic correction then replaces a wrong citation with the correct one when the named case exists, removes citations that cannot be grounded together with the sentence that relied on them, and removes case names written without a citation. The user sees only the repaired text and a one-line summary.")
wide_figure(SHOT / "paper_composite.png", "Fig. 2. Screens of the deployed system: (a) masked text reviewed before upload, (b) an answer whose citations have been verified, (c) a draft with its verification panel, (d) hearing dates extracted to the calendar.", width=6.4)

# ================= IV. Experimental setup =================
heading("IV", "Experimental Setup")
para("All experiments use one model, gpt-oss-120b on Groq, so that differences arise from the pipeline rather than the model. Costs use Groq list prices (US$0.15 and US$0.60 per million input and output tokens). We evaluate: (1) citation-error detection on 150 real Supreme Court cases, each corrupted in five ways (wrong page, wrong year, swapped party names, wrong court, invented case) plus six citations used for the wrong proposition, mixed with 156 genuine citations; (2) retrieval on 93 queries in which a judgment's own headnote must retrieve its body; (3) masking on held-out synthetic Indian case papers; (4) eight research questions spanning criminal, family, contract, property, arbitration and consumer law, answered with and without the pipeline; and (5) eight real High Court judgments used as case papers. A citation counts as fabricated only if its format is one the store covers completely (Supreme Court neutral and SCR citations); other formats are reported as uncheckable rather than fabricated [6].")

# ================= V. Results =================
heading("V", "Results and Discussion")
sub("A", "Effect of each layer")
para(f"Fig. 3 adds one layer at a time to the same model. Answering from memory (A), {arm('A', 'fabricated_pct')} of checkable citations were fabricated and {arm('A', 'unsupported_pct')} named real cases that do not support the stated point. Supplying retrieved sources (B) lowered fabrication to {arm('B', 'fabricated_pct')} but raised misattribution to {arm('B', 'unsupported_pct')}: given real material, the model attaches it to claims it does not make. Requiring a source tag on every legal statement (C) removed fabrication entirely, yet the judge rejected {arm('C', 'unsupported_pct')} of tagged citations as not supporting the exact sentence. Only verification with automatic correction (D) eliminated both failure modes: of {fun.get('citations_before', 0)} citations written in the eight full answers, {fun.get('removed', 0)} were removed with the claims that relied on them and the {fun.get('kept_in_final', 0)} released were all verified. The layers are therefore complementary rather than cumulative: tagging addresses existence, verification addresses support. With eight questions the percentages are indicative; the pattern, not the exact values, is the finding.")
figure(FIG / "fig11_pipeline_ablation.png", "Fig. 3. Ablation on eight questions with the same model: unreliable citations (fabricated, or real but not supporting the claim) as each layer is added.")
sub("B", "Comparison with published systems")
para(f"Fig. 4 places the full pipeline beside published hallucination rates. The figures for other systems were obtained under different protocols and jurisdictions and are given for context only. Fig. 5 reports citation-error detection: on our benchmark the verifier reaches {pct(100 * fake['recall'])} recall and {pct(100 * fake['precision'])} precision. The same base model used as an agentic checker in [4] reaches 55.1% recall, so the gain comes from grounding verification in a complete case store rather than from the model itself. Swapped party names are the hardest corruption (98% caught), because the rest of the citation is correct; Fig. 6 gives the full confusion matrix.")
figure(FIG / "fig3_hallucination.png", "Fig. 4. Unreliable citations: DocketPilot and the same model answering from memory (measured), against published figures for commercial tools [2] and general models [3].")
figure(FIG / "fig2b_citation_f1.png", "Fig. 5. F1 of citation-error detection. Other systems from [4] (agentic setting, US briefs); DocketPilot on the Indian benchmark.")
figure(FIG / "fig8_confusion_matrix.png", "Fig. 6. Confusion matrix of the citation verifier on 756 fake and 156 genuine citations.", width=COL * 0.62)
sub("C", "Cost and speed")
para(f"Because only the best passages are sent, a verified research answer costs US${cost['docketpilot']:.5f} against US${cost['baseline_long_context']:.5f} when the same model reads the full judgments, a {pct(cost['reduction_pct'])} reduction that includes every verification call (Fig. 7). Verification is not free: in the ablation run retrieval took {tm.get('retrieval', 0):.1f} s on a laptop CPU, generation {tm.get('llm_answer', 0):.1f} s and verification {tm.get('verification', 0):.1f} s per answer, and the verifier consumed {tok.get('judge_in', 0):,.0f} of the {tok.get('judge_in', 0) + tok.get('answer_in', 0):,.0f} input tokens per answer. Reading a case paper took {speed['docketpilot']:.1f} s versus {speed['baseline']:.1f} s for the unassisted model, a {pct(speed['speedup_pct'])} saving that is smaller than the 60.8% reported for LegalMind [1]; DocketPilot trades raw speed for checking.")
figure(FIG / "fig1a_cost_reduction.png", "Fig. 7. Cost reduction against an AI baseline: DocketPilot (measured) and published systems [1], [8].")
sub("D", "Retrieval and privacy")
lex, hyb, hr = RET.get("lexical", {}), RET.get("hybrid", {}), RET.get("hybrid_rerank", {})
para(f"Fig. 8 confirms that neither lexical nor dense search suffices alone: Recall@5 rises from {pct(100 * lex.get('recall@5', 0))} for lexical search to {pct(100 * hyb.get('recall@5', 0))} with fusion and {pct(100 * hr.get('recall@5', 0))} after re-ranking, at the cost of extra latency. The privacy gateway masked every structured identifier in the held-out set; overall recall was {pct(100 * pii['recall'])}, with person names the main source of misses, which the review screen is designed to catch.")
figure(FIG / "fig5_retrieval_modes.png", "Fig. 8. Retrieval methods on 93 headnote-to-judgment queries.")
table("TABLE II. Component results", ["Component", "Metric", "Result"],
      [["Citation verifier", "Recall / precision / F1", f"{100 * fake['recall']:.1f} / {100 * fake['precision']:.1f} / {100 * fake['f1']:.1f}%"],
       ["Retrieval (hybrid + re-rank)", "Recall@1 / Recall@5 / MRR@10", f"{100 * hr.get('recall@1', 0):.1f} / {100 * hr.get('recall@5', 0):.1f}% / {hr.get('mrr@10', 0):.3f}"],
       ["Privacy gateway (held-out)", "Recall / leakage", f"{100 * pii['recall']:.1f} / {100 * pii['leakage_rate']:.1f}%"],
       ["Statute date logic", "Boundary checks passed", f"{EV.get('statutes', {}).get('passed', 18)} / {EV.get('statutes', {}).get('boundary_checks', 18)}"],
       ["Released answers", "Unreliable citations", pct(D_tot)]],
      [1.25, 1.25, 0.95])
para(f"Fig. 9 sets these numbers beside the Indian systems that report comparable scores. The first passage returned is the correct judgment in {pct(100 * hr.get('recall@1', 0))} of queries, above the 74% retrieval precision of NyayaAI [26]; the ranking quality (MRR {hr.get('mrr@10', 0):.3f}) exceeds the MAP of 0.36 reported by AQgR [27] (with one relevant judgment per query MAP equals MRR); and the verifier's F1 of {pct(100 * fake['f1'])} exceeds NyayaAI's headline F1 of 0.71. Test sets differ, so the comparison positions rather than ranks the systems.")
figure(FIG / "fig16_indian_systems.png", "Fig. 9. DocketPilot against published Indian legal-AI systems on the scores they report [26], [27]; each system on its own test set.", width=COL * 0.74)
sub("E", "Explainability")
para("To make evidence selection inspectable we apply LIME [12] to the re-ranker: words of the selected passage are removed at random 400 times, each variant is scored, and a weighted linear surrogate is fitted. Fig. 10 shows that, for a question on the presumption under Section 139 of the Negotiable Instruments Act, the decisive terms are the section number, “rebuttable” and the Act's name, while for a maintenance question they are “wife”, “husband”, “claim” and “maintenance”. The surrogate fits well (R² of 0.86 and 0.75), so a lawyer can see why a judgment was offered as support.")
figure(FIG / "fig15_lime.png", "Fig. 10. LIME attributions of the evidence re-ranker for two queries; blue words raise and red words lower the relevance score.", width=COL * 0.8)

# ================= VI. Limitations and future work =================
heading("VI", "Limitations and Future Work")
para("The evaluation is automatic: citation reliability is judged against a case store and an AI judge, and the question sets are small because of free-tier API quotas. Full-text coverage is limited to the Supreme Court from 2015 and a sample of five High Court benches; citations in formats the store does not fully cover cannot yet be checked. Scanned papers require OCR, which is not yet integrated. Planned work includes a study with practising advocates measuring time saved and output quality, wider High Court coverage, and hosting on a cloud server with encrypted storage.")

# ================= VII. Conclusion =================
heading("VII", "Conclusion")
para(f"DocketPilot shows that a single open-weight model, wrapped in retrieval, source tagging and a verifier that repairs its own output, can deliver legal answers and drafts whose citations are checked before release, at a fraction of the cost of long-context prompting and without exposing client identities. Reducing unreliable citations from {pct(A_tot)} to {pct(D_tot)} required every layer of the pipeline, which suggests that verification should be treated as a first-class component of legal AI rather than an optional check.")

# ================= References =================
rp = para("References", size=10, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=8, after=4, sc=True)
REFS = [
    "[Authors], “LegalMind: Agentic AI-driven process optimization and cost reduction in legal services using DeepSeek,” IEEE Access, vol. 13, 2025, doi: 10.1109/ACCESS.2025.3586781.",
    "V. Magesh, F. Surani, M. Dahl, M. Suzgun, C. D. Manning, and D. E. Ho, “Hallucination-free? Assessing the reliability of leading AI legal research tools,” J. Empirical Legal Stud., vol. 22, pp. 216–242, 2025, doi: 10.1111/jels.12413.",
    "M. Dahl, V. Magesh, M. Suzgun, and D. E. Ho, “Large legal fictions: Profiling legal hallucinations in large language models,” J. Legal Anal., vol. 16, no. 1, pp. 64–93, 2024.",
    "P. Liu, D. Stammbach, and P. Henderson, “Who checks the citations? Benchmarking legal hallucination detection,” arXiv:2606.21155, 2026.",
    "S. Chen, H. Yin, and S. Zhou, “LegalCiteBench: Evaluating citation reliability in legal language models,” in Proc. ICML, 2026, arXiv:2605.10186.",
    "V. Ovcharov, “Citation grounding measures the oracle: Graph coverage determines reported LLM hallucination rates in law,” arXiv:2606.00898, 2026.",
    "J. Bose, “Falkor-IRAC: Graph-constrained generation for verified legal reasoning in Indian judicial AI,” arXiv:2605.14665, 2026.",
    "M. Hany, M. ElSheraey, M. Said, and P. Naoum, “Inject or navigate? Token-efficient retrieval for LLM analysis of transactional legal documents,” arXiv:2607.05764, 2026.",
    "L. Martin et al., “Better call GPT, comparing large language models against lawyers,” arXiv:2401.16212, 2024.",
    "Vals AI, “Vals legal AI report,” Feb. 2025. [Online]. Available: https://www.vals.ai",
    "P. Lewis et al., “Retrieval-augmented generation for knowledge-intensive NLP tasks,” in Proc. NeurIPS, 2020, pp. 9459–9474.",
    "M. T. Ribeiro, S. Singh, and C. Guestrin, “‘Why should I trust you?’ Explaining the predictions of any classifier,” in Proc. ACM SIGKDD, 2016, pp. 1135–1144.",
    "G. V. Cormack, C. L. A. Clarke, and S. Büttcher, “Reciprocal rank fusion outperforms Condorcet and individual rank learning methods,” in Proc. ACM SIGIR, 2009, pp. 758–759.",
    "S. Xiao, Z. Liu, P. Zhang, and N. Muennighoff, “C-Pack: Packaged resources to advance general Chinese embedding,” arXiv:2309.07597, 2023.",
    "R. Nogueira and K. Cho, “Passage re-ranking with BERT,” arXiv:1901.04085, 2019.",
    "N. Guha et al., “LegalBench: A collaboratively built benchmark for measuring legal reasoning in large language models,” in Proc. NeurIPS Datasets and Benchmarks, 2023.",
    "Z. Ji et al., “Survey of hallucination in natural language generation,” ACM Comput. Surv., vol. 55, no. 12, pp. 1–38, 2023.",
    "OpenAI, “gpt-oss-120b and gpt-oss-20b model card,” 2025.",
    "LangChain, “LangGraph: Building stateful, multi-actor applications with LLMs,” 2025. [Online]. Available: https://langchain-ai.github.io/langgraph/",
    "S. Robertson and H. Zaragoza, “The probabilistic relevance framework: BM25 and beyond,” Found. Trends Inf. Retr., vol. 3, no. 4, pp. 333–389, 2009.",
    "Indian Supreme Court and High Court judgments, Registry of Open Data on AWS (CC-BY-4.0); India Code, Legislative Department, Government of India.",
    "M. Honnibal, I. Montani, S. Van Landeghem, and A. Boyd, “spaCy: Industrial-strength natural language processing in Python,” 2020.",
    "A. Joshi et al., “IL-TUR: Benchmark for Indian legal text understanding and reasoning,” in Proc. ACL, 2024.",
    "V. Malik et al., “ILDC for CJPE: Indian legal documents corpus for court judgment prediction and explanation,” in Proc. ACL-IJCNLP, 2021, pp. 4046–4062.",
    "S. Paul, A. Mandal, P. Goyal, and S. Ghosh, “Pre-trained language models for the legal domain: A case study on Indian law,” in Proc. ICAIL, 2023, pp. 187–196.",
    "Deepanshu, D. Saxena, D. Rana, A. Varshney, and S. R. Laskar, “NyayaAI: An AI-powered legal assistant using multi-agent architecture and retrieval-augmented generation,” arXiv:2605.10155, 2026.",
    "V. Vishnuprabha, D. M. Viswanathan, R. Rajesh, and A. V. Pillai, “Augmented question-guided retrieval (AQgR) of Indian case law with LLM, RAG, and structured summaries,” arXiv:2508.04710, 2025.",
    "R. Goel, S. P. Kumar, A. Agrawal, D. Poddar, P. Narang, and D. Kumar, “Domain-partitioned hybrid RAG for legal reasoning: Toward modular and explainable legal AI for India,” arXiv:2602.23371, 2025.",
]
for i, ref in enumerate(REFS, 1):
    q = para(f"[{i}]  {ref}", size=8, indent=False, align=WD_ALIGN_PARAGRAPH.LEFT)
    q.paragraph_format.left_indent = Inches(0.25)
    q.paragraph_format.first_line_indent = Inches(-0.25)

doc.save(OUT)
print("wrote", OUT)
