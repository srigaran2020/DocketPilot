# ruff: noqa: E501  (prose)
"""Text of the DocketPilot project report (chapters after the Table of Contents). Numbers come from reports/*.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REP = ROOT / "reports"
FIG = REP / "figures"
SHOT = REP / "screenshots"
HERE = Path(__file__).resolve().parent


def _j(name):
    p = REP / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


EV, KB, AB, BV = _j("evaluation.json"), _j("kb_composition.json"), _j("ablation.json"), _j("benchmark_vs.json")
FAKE = EV["fake_citations"]["overall"]
PT = EV["fake_citations"]["per_type"]
RET = EV["retrieval"]
PII = EV["pii"]["heldout_with_ner"]
LAT = EV["latency"]
COST = BV["summary"]["cost_per_answer_usd"]
SPEED = BV["summary"]["document_processing_seconds"]
CIT = BV["summary"]["citations"]
ARMS = {a["arm"]: a for a in AB.get("arms", [])} if isinstance(AB.get("arms"), list) else AB.get("arms", {})


def arm(k, f):
    a = ARMS.get(k, {})
    if f == "total_pct":
        return a.get("fabricated_pct", 0.0) + a.get("unsupported_pct", 0.0)
    return a.get(f, 0.0)


def pct(x, d=1):
    return f"{x:.{d}f}%"


n = lambda v: f"{v:,}"  # noqa: E731
HR = RET["hybrid_rerank"]
FUN = AB.get("funnel", {})
TM = AB.get("timing_mean_s", {})

ABSTRACT = (
    "Large language models can draft legal text fluently, but they also invent judgments, misquote passages and cite "
    "provisions that are no longer in force, and they normally require client papers to be sent to a hosted model. This "
    "project presents DocketPilot, an agentic AI system for Indian legal research, drafting, anti-hallucination "
    "verification and case management. Seven agents coordinated by a LangGraph state graph analyse case papers, "
    "retrieve statutes and judgments, draft documents with a source tag on every legal statement, verify and repair "
    "every citation, list risks and missing facts, and derive deadlines for a hearing calendar. A local privacy gateway "
    "masks names and identity numbers before any text reaches the model, and the real names are restored only after the "
    "lawyer approves the output. The knowledge base holds "
    f"{n(KB.get('judgments_total', 0))} Supreme Court and High Court judgments with full text, {KB.get('acts', 79)} Central "
    f"Acts and {n(KB.get('vectors', 0))} searchable passages. On a benchmark of {FAKE['fakes']} corrupted and "
    f"{FAKE['reals']} genuine citations the verifier reached {pct(100 * FAKE['recall'])} recall and "
    f"{pct(100 * FAKE['precision'])} precision. With the same model, the full pipeline reduced unreliable citations "
    f"from {pct(arm('A', 'total_pct'))} to {pct(arm('D', 'total_pct'))} and cut the cost of a verified answer by "
    f"{pct(COST['reduction_pct'])} compared with sending whole judgments to the model."
)
KEYWORDS = ("Large Language Models (LLMs), Agentic AI, Retrieval-Augmented Generation (RAG), Legal Hallucination, "
            "Citation Verification, LangGraph, Privacy-Preserving NLP, Indian Legal Informatics, Explainable AI (LIME)")

INTRO = [
    "Artificial Intelligence (AI) is increasingly used in professional fields to search information, analyse documents and support decision-making. In legal practice, advocates read statutes, court judgments, case files, contracts and notices before they prepare arguments or advise clients. AI tools can help with legal research, summarisation and first drafts, and so reduce repetitive work. Legal work, however, demands accuracy, traceable sources, confidentiality and professional judgment. A legal AI system must therefore do more than generate fluent text: every statement it makes about the law must be checkable.",
    "A major weakness of generative AI is hallucination, where a model produces convincing but incorrect or unsupported content. In law this takes the form of judgments that do not exist, real judgments cited for a point they never decided, wrong page or year numbers, misquoted passages and sections that have been repealed or renumbered. Studies of general models have measured hallucination rates between 69% and 88% on verifiable questions about court cases, and even commercial research tools that use retrieval still produce misgrounded answers in 17% to 33% of cases. Such errors can mislead a court and expose the advocate to professional consequences, so the output of a model cannot be trusted without an independent check against the original sources.",
    "The problem is sharper in India. Research involves Central Acts and their amendments, the move from the Indian Penal Code, Code of Criminal Procedure and Evidence Act to the Bharatiya Nyaya Sanhita, Bharatiya Nagarik Suraksha Sanhita and Bharatiya Sakshya Adhiniyam in 2024, and judgments of the Supreme Court and many High Courts reported in several citation formats (SCC, SCR, AIR and neutral citations). The provision that applies depends on the date of the offence or the cause of action. A useful assistant must retrieve material from identifiable sources, keep the date on which a provision was in force, and confirm every citation against the judgment itself before it shows a result to the lawyer.",
    "Confidentiality adds a second constraint. Case papers carry names, Aadhaar and PAN numbers, bank accounts, telephone numbers and addresses. Sending these to a hosted model would breach the duty of confidence that an advocate owes a client. Any practical system must keep identities on the lawyer's own machine and give the model only masked text.",
    "DocketPilot: An Agentic AI System for Indian Legal Research, Drafting, Anti-Hallucination Verification and Case Management addresses these problems with a coordinated multi-agent architecture. A LangGraph state graph runs seven specialised agents for orchestration, document analysis, research, drafting, verification, strategy and risk, and deadline monitoring, and it pauses for the advocate's approval before any document is released. A single conversational interface routes ordinary questions to verified research answers, similar-case search, verification of pasted text and reminders, while drafting requests start the full agent graph.",
    "The knowledge base is built offline from the open Supreme Court and High Court judgment collections published under the CC-BY-4.0 licence and from Central Acts published on India Code. Judgments are cleaned, split into headnote and body, cut into passages and indexed twice: in PostgreSQL for keyword search and in the Qdrant vector database for meaning-based search. Retrieval-Augmented Generation (RAG) supplies the most relevant passages to the language model, gpt-oss-120b served through Groq, which is the only generative model in the system.",
    "Before any text reaches the model, a privacy gateway replaces identities with placeholders such as PERSON_1 and ORG_2. It uses rule patterns with checksums for structured identifiers and a named-entity model for names. The advocate reviews the masked text, and the mapping from placeholder to real name is kept in an encrypted vault on the local machine. After generation, a verification engine extracts every citation, quotation and statutory reference, resolves it against the case store, checks quotations word for word, asks a separate judge prompt whether the cited passage supports the sentence, and confirms that each section was in force on the relevant date. Automatic correction then repairs wrong citation strings and removes claims that cannot be grounded, so the lawyer receives only checked text.",
    "For case management, DocketPilot stores each matter as a case file with its papers, facts, drafts and an audit log. Dates found in the papers are filed to a hearing calendar, each anchored to the sentence it came from, and approved drafts are exported as Word documents with the real names restored. The system runs locally with Docker, uses role-based accounts for advocates and juniors, and was evaluated on citation-error detection, retrieval quality, privacy masking, answer reliability, cost and speed. The objective is a reliable, verifiable and privacy-conscious assistant for Indian legal practice, in which the advocate remains responsible for every document that is filed.",
]

LIT_INTRO = "The following studies were selected from academic and research sources relevant to legal hallucinations, reliability of AI legal research tools, judicial AI applications, Indian legal assistants and automated detection of unsupported legal content. The techniques and findings below summarise the cited publications."

# Rows 6 onwards (rows 1 to 5 are kept from the original report, cleaned)
LIT_NEW = [
    ["Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools", "Journal of Empirical Legal Studies", "2025",
     "Pre-registered evaluation of retrieval-augmented commercial tools (Lexis+ AI, Westlaw AI-Assisted Research, Ask Practical Law AI) with human grading of answers.",
     "Retrieval reduces but does not remove hallucination: 17% of Lexis+ AI and 33% of Westlaw answers were incorrect or misgrounded. Citing a real case for the wrong proposition was a frequent failure, which motivates checking support and not only existence."],
    ["Who Checks the Citations? Benchmarking Legal Hallucination Detection", "arXiv preprint", "2026",
     "Benchmark of citation-error detection on excerpts of legal briefs; models used as agentic checkers with search tools.",
     "The best agentic configuration caught 84.4% of bad citations and the best F1 was 68.8%. The same open model used by DocketPilot (gpt-oss-120b) caught 55.1% when used alone, so a checker grounded in a complete case store is needed."],
    ["NyayaAI: An AI-Powered Legal Assistant Using Multi-Agent Architecture and Retrieval-Augmented Generation", "arXiv preprint", "2026",
     "Multi-agent orchestration with a domain classifier, FAISS semantic retrieval over Indian statutes and case law, and a compliance check before delivery.",
     "Reports 74% retrieval precision, 72% response accuracy and an F1 of 0.71. It does not verify the citations it emits or mask client data, and the test-set size is not reported."],
]

LIT_GAP = [
    "The survey shows three gaps. First, retrieval alone does not make legal answers reliable: commercial retrieval tools still misground a sixth to a third of their answers, and the most common failure is a real authority cited for a point it does not support. Second, existing Indian assistants such as Neethi AI and NyayaAI focus on retrieval, routing and accessibility, and none of them verifies each citation against the judgment text or repairs the output automatically. Third, client confidentiality is treated as a limitation rather than designed into the pipeline. DocketPilot is built to close these gaps by combining retrieval, source-tagged drafting, citation verification with automatic correction, and local privacy masking in one application for Indian lawyers.",
]
LIT_TABLE = ("Table 2.1 Feature comparison of DocketPilot with related systems",
             ["System", "Users", "Retrieval", "Citation check", "Auto-repair", "PII masking", "Calendar"],
             [["DocketPilot", "Lawyers", "Hybrid + re-rank", "Yes", "Yes", "Local, encrypted", "Yes"],
              ["Neethi AI", "Citizens", "BGE-M3 + BM25", "Yes", "No", "Listed as a limitation", "No"],
              ["NyayaAI", "General", "FAISS dense", "No", "No", "No", "No"],
              ["LegalMind", "Firms", "Not reported", "No", "No", "No", "No"],
              ["Lexis+ AI", "Lawyers (US)", "Proprietary", "No", "No", "No", "No"]],
             [1500, 1100, 1500, 1150, 1100, 1500, 1176])

M = {}  # methodology sections: key -> list of blocks
M["3"] = [
    ("p", "The methodology follows the path of a request through the system. Section 3.1 presents the overall architecture. Sections 3.2 to 3.6 describe each stage in the order in which it acts on the data: building the knowledge base, masking client documents, running the agent graph, retrieving evidence, and verifying and correcting the output. Section 3.7 explains how the system was evaluated."),
]
M["3.1"] = [
    ("p", "DocketPilot is organised in five layers (Fig. 3.1). The user layer is a single-page web application through which an advocate or junior signs in, attaches case papers, reviews the masking, asks questions, reads verified results and approves drafts. The backend layer is a FastAPI service written in Python. It authenticates users with JSON Web Tokens, keeps every firm's data separate, writes an append-only audit log, and hosts the privacy gateway and a rule-based chat router that decides which tool should answer a message."),
    ("fig", HERE / "block_diagram.png", 5.4, "Fig. 3.1 Block diagram of DocketPilot"),
    ("p", "The agent layer is a LangGraph state graph with seven agents. Its state is saved to PostgreSQL after every step, so a run can resume after a crash or a restart, and it pauses at an approval interrupt so that nothing leaves the system without the advocate's consent. The retrieval and model layer contains the tiered retriever, the language model gpt-oss-120b served by Groq, and the verification engine. The data layer holds PostgreSQL 16 (cases, passages, statutes, case files, audit records and graph checkpoints), the Qdrant vector database, and the encrypted vault that maps placeholders to real names."),
    ("p", "Fig. 3.2 shows the complete workflow across the lanes: the lawyer's actions, the frontend screens, the backend services, the LangGraph agents, the verification steps, and the data and models each step uses. The following sections describe the stages in the order in which a request passes through them."),
    ("fig", HERE / "workflow_rotated.png", 4.15, "Fig. 3.2 End-to-end workflow of DocketPilot"),
    ("table", "Table 3.1 Technology stack", ["Layer", "Component", "Purpose"],
     [["Frontend", "HTML, CSS, JavaScript (single page)", "Chat, masking review, drafts, calendar, dashboard"],
      ["Backend", "FastAPI, Python 3.11", "REST API, authentication, routing, audit log"],
      ["Agents", "LangGraph", "Seven-agent state graph with checkpoints and approval interrupt"],
      ["Language model", "gpt-oss-120b on Groq", "Answers, drafts and support judgments on masked text"],
      ["Relational store", "PostgreSQL 16", "Cases, passages, statutes, full-text search, case files"],
      ["Vector store", "Qdrant 1.12", "Dense passage vectors (bge-small-en-v1.5, 384 dimensions)"],
      ["Re-ranker", "MiniLM cross-encoder", "Re-orders retrieved passages by relevance"],
      ["Privacy", "Regex with checksums, spaCy NER, Fernet", "Masking, review and encrypted placeholder vault"],
      ["Deployment", "Docker Compose", "PostgreSQL, Qdrant, Redis and object store on one machine"]],
     [1800, 3300, 3926]),
]
M["3.2"] = [
    ("p", "The knowledge base is built once, offline, from public sources. Supreme Court judgments and High Court judgments of five benches (Kerala, Karnataka, Telangana, Madras and its Madurai bench) are taken from the open Indian judgment collections on the AWS Registry of Open Data, which are released under the CC-BY-4.0 licence. Central Acts, their sections and their amendment footnotes are taken from India Code, published by the Legislative Department of the Government of India."),
    ("p", "Each judgment passes through a fixed preparation pipeline. The text is cleaned of page furniture, and the headnote written by the law reporter is separated from the body of the judgment. The headnote is stored as its own segment and is never used as evidence, because it is not the court's own words. The body is cut into overlapping passages, each tagged with its page so that a citation can point to the exact place. Case names, dates, courts and every reported citation (neutral, SCR, SCC and AIR) are normalised into a single case record so that any form of a citation can be resolved to the same judgment. Citations between judgments are extracted into a citation graph that is later used to check whether a precedent has been overruled or doubted."),
    ("p", f"Statutes are stored section by section with the dates from which each version was in force, so the system can answer what a section said on a given date. Every rule file that encodes a legal deadline or limitation quotes the statute, and an automatic test checks that the quoted words really occur in the India Code text. The resulting store holds {n(KB.get('cases_total', 0))} cases for citation resolution, {n(KB.get('judgments_total', 0))} judgments with full text, {KB.get('acts', 79)} Central Acts with {n(KB.get('sections', 0))} sections, and {n(KB.get('chunks', 0))} passages, of which {n(KB.get('vectors', 0))} are embedded for vector search (Fig. 3.3)."),
    ("fig", FIG / "fig10_knowledge_base.png", 4.3, "Fig. 3.3 Composition of the knowledge base by court"),
    ("table", "Table 3.2 Contents of the knowledge base", ["Item", "Count", "Source"],
     [["Cases available for citation resolution", n(KB.get("cases_total", 0)), "Supreme Court 1950-2026, High Courts 2022-2025"],
      ["Judgments with full text", n(KB.get("judgments_total", 0)), "AWS Open Data (CC-BY-4.0)"],
      ["Central Acts / sections", f"{KB.get('acts', 79)} / {n(KB.get('sections', 0))}", "India Code"],
      ["Passages (keyword index)", n(KB.get("chunks", 0)), "PostgreSQL full-text search"],
      ["Passages with vectors", n(KB.get("vectors", 0)), "Qdrant, bge-small-en-v1.5"]],
     [3600, 1700, 3726]),
]
M["3.3"] = [
    ("p", "Client papers enter the system only through the privacy gateway. An uploaded PDF, Word or text file is converted to plain text and scanned by two recognisers. The first uses rule patterns with checksums for structured identifiers: Aadhaar numbers (validated with the Verhoeff checksum), PAN, bank account and IFSC codes, telephone, vehicle registration numbers, e-mail addresses and postal addresses. The second is a spaCy named-entity model that finds the names of people and organisations. Every value found is replaced by a consistent placeholder, so that the same person becomes PERSON_1 everywhere in the case file and the model can still reason about who did what."),
    ("p", "The masked text is shown to the advocate before it is stored, with each placeholder highlighted. The advocate can untick a mask that is not needed or mark a name the recogniser missed. Only after this review is the masked text saved and made available to the agents. The mapping from placeholder to real value is encrypted with Fernet (AES in CBC mode with an HMAC) under a key held in the local environment file, and it is stored per case file. Real names are restored only on the advocate's screen and in the approved Word document, so the language model never receives an identity."),
    ("p", "When the papers are analysed, the document-analysis agent extracts facts such as the parties, the cheque or agreement details and the important dates, and it keeps a fact only if the sentence that supports it is found in the papers. Each date is filed to the case calendar together with that quote, so the lawyer can see where every reminder came from."),
]
M["3.4"] = [
    ("p", "Drafting requests start the LangGraph workflow, in which each agent is a node that reads and writes a typed shared state. The agents and their responsibilities are listed in Table 3.3. The graph runs them in order, with time limits and retries for each node, and it saves the state after every step."),
    ("table", "Table 3.3 Agents of the LangGraph workflow", ["Agent", "Input", "Output"],
     [["1 Orchestrator", "Request and case file", "Workflow plan, document type and court"],
      ["2 Document analysis", "Masked papers", "Facts, each with a supporting quote"],
      ["3 Research", "Facts and issues", "Statute sections in force and re-ranked judgment passages"],
      ["4 Drafting", "Facts and sources", "Draft with a source tag on every legal statement"],
      ["5 Verification", "Draft", "Checked and repaired draft with a verdict for each citation"],
      ["6 Strategy and risk", "Facts and draft", "Missing facts, weak points and similar past cases"],
      ["7 Monitoring", "Facts and statutes", "Statutory deadlines and reminders"],
      ["Approval and finalize", "Advocate's decision", "Released Word document with real names restored"]],
     [2400, 2700, 3926]),
    ("p", "The drafting agent never states law without a source. It writes tags such as [P1] or [S2] after each legal statement, which refer to the retrieved passage or statute section that supports it, and the system replaces each tag with the proper citation afterwards. Because the model only chooses among sources that were actually retrieved, it cannot invent a citation string. The verification agent cannot be skipped: if it fails or times out, nothing is released."),
    ("p", "After monitoring, the graph stops at an approval interrupt. The advocate reads the draft beside its evidence panel, ticks any item flagged for acknowledgement, edits the text if needed and approves it. An edit sends the draft back through verification. On approval, the finalize step restores the real names from the vault, produces the Word file and adds the deadlines to the calendar. Questions that do not need a full draft, such as a research question, a request for similar cases or a request to verify pasted text, are answered directly by the chat router using the same retrieval and verification components."),
]
M["3.5"] = [
    ("p", "Retrieval proceeds from exact to fuzzy so that the cheapest reliable method is used first. An exact citation in the question is looked up directly in the case store, and a reference to a section is answered from the statute table as on the relevant date. For open questions, two searches run in parallel. PostgreSQL full-text search ranks passages by keyword overlap, and dense search in Qdrant finds passages with similar meaning, using 384-dimensional bge-small-en-v1.5 embeddings stored as 8-bit integers to save memory."),
    ("p", "The two ranked lists are combined by reciprocal rank fusion, which adds 1/(k + rank) for every list in which a passage appears, so a passage that ranks well in both lists rises to the top. The fused candidates are then re-scored by a MiniLM cross-encoder that reads the question and the passage together. Finally, the retrieved text is fitted to a fixed token budget so that a single request to Groq stays within the provider's limit of 8,000 tokens per request on the free tier. Every passage keeps its case, page and paragraph so that the final citation can point to the exact place."),
    ("p", "Requests to the model are sent through a client that rotates among several API keys, retries on rate limits and stops cleanly when the daily quota is reached. Only masked text is ever sent, and the model is asked for structured JSON whose fields are validated before use."),
]
M["3.6"] = [
    ("p", "Every chat answer, every draft and any text pasted by the user passes through the same verification engine. Its steps are deterministic database lookups and string comparisons, with a single step that uses the language model. First, every citation, quotation and statutory reference is extracted. Citations are normalised (for example, \"(2021) 5 SCC 283\" and \"2021 INSC 529\") and resolved against the case store by exact key, then by alias, then by name and year. Each citation receives a verdict: verified, partial, conflict (the details point to different judgments) or not found."),
    ("p", "Quotations are compared with the judgment text and marked exact, near or absent. For each citation that exists, a separate judge prompt is shown the cited passage and the sentence that relies on it, and it must answer whether the passage supports the sentence, quoting the passage as proof; an answer without a matching quote is rejected. The citation graph is then consulted to see whether the judgment has been overruled or doubted by later cases, and every statutory reference is checked to confirm that the section exists and was in force on the relevant date."),
    ("p", "Automatic correction acts on the verdicts. When the named case exists but the citation string is wrong, the correct citation replaces it. When a citation cannot be grounded, or the judge finds that the passage does not support the sentence, the citation is removed together with the sentence that relied on it, and case names written without any citation are removed. The release gate then marks the output as verified, as needing acknowledgement, or as blocked. The user sees only the repaired text and a one-line summary such as \"10 references checked, 4 removed\" (Fig. 3.4)."),
    ("fig", FIG / "fig14_autocorrect_outcomes.png", 4.0, "Fig. 3.4 Outcomes of automatic correction across the evaluation answers"),
]
M["3.7"] = [
    ("p", "All experiments use one model, gpt-oss-120b on Groq, so that differences come from the pipeline rather than from the model. Costs are computed from the token counts returned by the API at Groq list prices (US$0.15 per million input tokens and US$0.60 per million output tokens). Six evaluations were carried out."),
    ("bul", [
        f"Citation-error detection: {PT['real']['n']} real Supreme Court citations, each corrupted in five ways (wrong page, wrong year, swapped party names, wrong court and an invented case), plus citations used for the wrong proposition, giving {FAKE['fakes']} faulty and {FAKE['reals']} genuine citations.",
        f"Retrieval: {RET['n_queries']} queries in which the headnote of a judgment must retrieve the body of the same judgment, measured by Recall@1, Recall@5 and mean reciprocal rank (MRR@10).",
        f"Privacy masking: {PII['planted_values']} identifiers planted in held-out synthetic Indian case papers, measured by recall and leakage.",
        "Pipeline ablation: eight research questions across criminal, family, contract, property, arbitration and consumer law answered by the model alone, with retrieval, with source tags, and with the full pipeline.",
        "Cost and speed: the same questions answered by DocketPilot and by the same model reading the full judgments, and eight real High Court judgments processed as case papers.",
        "Explainability: LIME applied to the passage re-ranker for two questions.",
    ]),
    ("p", "A citation is counted as fabricated only if its format is one that the store covers completely (Supreme Court neutral and SCR citations). Citations in other formats are reported as not checkable rather than as fabricated, because a missing entry in an incomplete store does not prove that a judgment does not exist."),
]

R = {}
R["4"] = [("p", "This chapter first shows the working application and then reports the measured results of the evaluations described in Section 3.7.")]
R["4.1"] = [
    ("p", "The screens below were captured from the running system with synthetic case papers. Fig. 4.1 shows the sign-in page, which supports e-mail accounts and Google sign-in. After a file is attached, the masking review (Fig. 4.2) lists every identifier that will be hidden from the model, and the advocate can untick or add masks before the text is stored."),
    ("fig2", [(SHOT / "s1_signin.png", "Fig. 4.1 Sign-in page"), (SHOT / "s2_masking_review.png", "Fig. 4.2 Masking review before upload")]),
    ("p", "Fig. 4.3 shows a research answer on divorce on the ground of cruelty and the wife's claim to maintenance. Each statement carries a citation that has been checked, and the summary line reports that ten references were checked and four were removed because their passages did not support the sentence. Fig. 4.4 shows a petition drafted by the agent graph with its verification panel, which states that the draft is clear to approve and lists the facts that are still needed before filing."),
    ("fig2", [(SHOT / "s3_verified_answer.png", "Fig. 4.3 Verified research answer"), (SHOT / "s6_draft_verification.png", "Fig. 4.4 Draft with verification panel")]),
    ("p", "Dates found in the papers are filed to the hearing calendar (Fig. 4.5), each with the quote it came from. The statute finder (Fig. 4.6) searches the Central Acts by topic and shows the text of each section, and the dashboard (Fig. 4.7) lists the advocate's case files, drafts awaiting approval and upcoming deadlines."),
    ("fig2", [(SHOT / "s4_calendar.png", "Fig. 4.5 Hearing calendar"), (SHOT / "s5_find_section.png", "Fig. 4.6 Statute finder")]),
    ("fig", SHOT / "s7_dashboard.png", 4.6, "Fig. 4.7 Case dashboard"),
]
R["4.2"] = [
    ("p", f"Fig. 4.8 adds one layer at a time to the same model. Answering from memory (A), {pct(arm('A', 'fabricated_pct'))} of checkable citations were fabricated and {pct(arm('A', 'unsupported_pct'))} named real cases that do not support the stated point. Supplying retrieved passages (B) lowered fabrication to {pct(arm('B', 'fabricated_pct'))} but raised misattribution to {pct(arm('B', 'unsupported_pct'))}: given real material, the model attached it to claims it does not make. Requiring a source tag on every statement (C) removed fabrication completely, yet the judge rejected {pct(arm('C', 'unsupported_pct'))} of tagged citations as not supporting the exact sentence. Only verification with automatic correction (D) removed both failures: of {FUN.get('citations_before', 0)} citations written in the full answers, {FUN.get('removed', 0)} were removed with the claims that relied on them, and all {FUN.get('kept_in_final', 0)} released citations were verified."),
    ("fig", FIG / "fig11_pipeline_ablation.png", 4.3, "Fig. 4.8 Unreliable citations as each layer of the pipeline is added"),
    ("p", "The layers are therefore complementary rather than cumulative. Source tagging solves the problem of existence, because the model can only cite what was retrieved, while verification solves the problem of support. With eight questions the percentages are indicative; the pattern, not the exact values, is the main finding."),
]
R["4.3"] = [
    ("p", f"On the citation benchmark the verifier reached {pct(100 * FAKE['recall'])} recall, {pct(100 * FAKE['precision'])} precision and an F1 score of {pct(100 * FAKE['f1'])}. Invented cases, wrong courts, wrong years and wrong pages were all caught (Fig. 4.9). Swapped party names were the hardest corruption, with {pct(100 * PT['swapped_names']['caught_rate'], 0)} caught, because the rest of the citation is correct. Among genuine citations, {pct(100 * PT['real']['false_alarm_rate'])} were flagged, mostly as partial matches that ask the lawyer to look again rather than blocking the citation. Fig. 4.10 gives the confusion matrix."),
    ("fig2", [(FIG / "fig7_error_types.png", "Fig. 4.9 Faulty citations caught by type"), (FIG / "fig8_confusion_matrix.png", "Fig. 4.10 Confusion matrix of the verifier")]),
    ("p", "Fig. 4.11 compares the F1 score with published citation checkers. The same base model used as an agentic checker in a recent benchmark reached 55.1% recall and 30.5% F1, so the improvement comes from grounding the check in a complete case store and not from the model itself. Fig. 4.12 places DocketPilot's released answers beside published hallucination rates; the figures for other systems come from different jurisdictions and protocols and are given for context."),
    ("fig2", [(FIG / "fig2b_citation_f1.png", "Fig. 4.11 F1 of citation-error detection"), (FIG / "fig3_hallucination.png", "Fig. 4.12 Unreliable citations compared")]),
]
R["4.4"] = [
    ("p", f"Fig. 4.13 compares the retrieval methods. Keyword search alone found the right judgment in the top five for {pct(100 * RET['lexical']['recall@5'])} of queries and vector search for {pct(100 * RET['dense']['recall@5'])}; fusing the two raised Recall@5 to {pct(100 * RET['hybrid']['recall@5'])}, and re-ranking raised it to {pct(100 * HR['recall@5'])} with an MRR of {HR['mrr@10']:.3f}. Re-ranking costs time on a laptop CPU (Fig. 4.14), but exact citation lookups take {LAT['exact_citation_lookup']['p95_ms']} ms and statute look-ups {LAT['statute_as_on']['p95_ms']} ms at the 95th percentile, well inside the 50 ms target."),
    ("fig2", [(FIG / "fig5_retrieval_modes.png", "Fig. 4.13 Retrieval methods compared"), (FIG / "fig6_speed_accuracy.png", "Fig. 4.14 Speed and accuracy of search")]),
    ("p", f"The privacy gateway masked every structured identifier in the held-out papers: Aadhaar, PAN, bank, IFSC and telephone numbers all reached 100% recall (Fig. 4.15). Overall recall was {pct(100 * PII['recall'])}; the misses were person names, which the review screen is designed to catch before anything is stored. Precision was {pct(100 * PII['precision'])}, meaning some extra words were masked, which is the safe direction for confidentiality."),
    ("fig", FIG / "fig9_privacy_types.png", 4.0, "Fig. 4.15 Recall of the privacy gateway by type of identifier"),
]
R["4.5"] = [
    ("p", f"Because only the best passages are sent, a verified research answer cost US${COST['docketpilot']:.5f} against US${COST['baseline_long_context']:.5f} when the same model read the full judgments, a reduction of {pct(COST['reduction_pct'])} that already includes every verification call (Fig. 4.16). This reduction is larger than the 25% to 67.5% reported for structured navigation and embedding retrieval and the 42.6% reported for LegalMind. Fig. 4.17 shows the cost of one thousand answers."),
    ("fig2", [(FIG / "fig1a_cost_reduction.png", "Fig. 4.16 Cost reduction against an AI baseline"), (FIG / "fig4_cost.png", "Fig. 4.17 Cost per 1,000 research answers")]),
    ("p", f"Verification is not free. In the ablation run, retrieval took {TM.get('retrieval', 0):.1f} s per answer on a laptop CPU, generation {TM.get('llm_answer', 0):.1f} s and verification {TM.get('verification', 0):.1f} s (Fig. 4.18), and the judge prompts used almost as many tokens as the answer itself (Fig. 4.19). Reading a case paper took {SPEED['docketpilot']:.1f} s against {SPEED['baseline']:.1f} s for the unassisted model, a saving of {pct(SPEED['speedup_pct'])}. DocketPilot trades some raw speed for checking every statement."),
    ("fig2", [(FIG / "fig12_time_breakdown.png", "Fig. 4.18 Time per answer by stage"), (FIG / "fig13_token_breakdown.png", "Fig. 4.19 Tokens per answer")]),
]
R["4.6"] = [
    ("p", f"Table 4.1 sets DocketPilot beside the Indian systems that report comparable scores, and Fig. 4.20 shows the same comparison. The first passage returned is the correct judgment in {pct(100 * HR['recall@1'])} of queries, above the 74% retrieval precision reported by NyayaAI. The ranking quality (MRR {HR['mrr@10']:.3f}) is well above the mean average precision of 0.36 reported by AQgR; when each query has one correct judgment, the two measures coincide. The verifier's F1 of {pct(100 * FAKE['f1'])} is above NyayaAI's headline F1 of 0.71. Each system was evaluated on its own test set, so the comparison positions the systems rather than ranking them. Neethi AI reports qualitative results without comparable numbers and is therefore compared by features in Table 2.1."),
    ("table", "Table 4.1 Comparison with published Indian legal-AI systems", ["Measure", "Other system", "Reported", "DocketPilot"],
     [["Retrieval precision (top result)", "NyayaAI", "74%", pct(100 * HR["recall@1"])],
      ["Headline F1", "NyayaAI", "0.71", f"{FAKE['f1']:.3f}"],
      ["Ranking quality (MAP / MRR)", "AQgR", "0.36", f"{HR['mrr@10']:.3f}"],
      ["Cost reduction vs. full documents", "LegalMind", "42.6%", pct(COST["reduction_pct"])],
      ["Fabricated citations in answers", "Same model alone", pct(100 * CIT["baseline_closed_book"]["fabricated_rate"]), pct(100 * CIT["docketpilot"]["fabricated_rate"])]],
     [3100, 2000, 1700, 2226]),
    ("fig", FIG / "fig16_indian_systems.png", 4.1, "Fig. 4.20 DocketPilot against published Indian legal-AI systems"),
]
R["4.7"] = [
    ("p", "To make the choice of evidence inspectable, LIME (Local Interpretable Model-agnostic Explanations) was applied to the passage re-ranker. Words of the selected passage were removed at random 400 times, each variant was scored by the re-ranker, and a weighted linear model was fitted to the scores; its coefficients show how much each word contributed. For a question on the presumption under Section 139 of the Negotiable Instruments Act, the strongest words were the section number, \"rebuttable\", \"negotiable\" and \"accused\". For a maintenance question they were \"wife\", \"husband\", \"claim\" and \"maintenance\" (Fig. 4.21)."),
    ("fig", FIG / "fig15_lime.png", 4.3, "Fig. 4.21 LIME explanation of the evidence re-ranker"),
    ("p", "The linear model explains the re-ranker well, with R squared values of 0.86 and 0.75, so the explanation can be trusted. It shows that the evidence selector relies on the legally decisive words and not on incidental ones, and it lets an advocate see why a particular judgment was offered as support."),
]

CONCLUSION = [
    ("p", "DocketPilot shows that a single open-weight language model, placed inside a pipeline of retrieval, source-tagged drafting and a verifier that repairs its own output, can produce legal answers and drafts whose every citation is checked before the lawyer sees it. The full pipeline reduced unreliable citations from " + pct(arm('A', 'total_pct')) + " for the model alone to " + pct(arm('D', 'total_pct')) + ", the verifier detected " + pct(100 * FAKE['recall']) + " of faulty citations with " + pct(100 * FAKE['precision']) + " precision, and a verified answer cost " + pct(COST['reduction_pct']) + " less than sending whole judgments to the model. Client identities never left the local machine, and the advocate approved every document before release."),
    ("p", "The ablation study gave the clearest lesson of the project: each layer fixes a different failure. Retrieval reduces invented cases but encourages real cases to be cited for the wrong point; source tags remove invention; and only verification with automatic correction removes misattribution. Verification should therefore be treated as a core component of legal AI and not as an optional extra."),
    ("h", "FUTURE WORK"),
    ("bul", [
        "A study with practising advocates measuring time saved and the quality of the drafts.",
        "Wider High Court coverage and complete coverage of SCC and AIR citations, so that every citation format can be checked.",
        "Optical character recognition for scanned case papers, with the same masking review.",
        "Support for Tamil, Hindi and other Indian languages in the interface and in the papers.",
        "Hosting on a cloud server with encrypted storage and firm-level key management.",
        "Larger evaluation sets once higher API quotas are available.",
    ]),
]

REFERENCES = [
    "LegalMind: Agentic AI-driven process optimization and cost reduction in legal services using DeepSeek, IEEE Access, vol. 13, 2025, doi: 10.1109/ACCESS.2025.3586781.",
    "Neethi AI: An AI-powered multi-agent system for Indian legal advisory, IEEE Conference Publication, 2026.",
    "V. Magesh, F. Surani, M. Dahl, M. Suzgun, C. D. Manning and D. E. Ho, \"Hallucination-free? Assessing the reliability of leading AI legal research tools,\" Journal of Empirical Legal Studies, vol. 22, pp. 216-242, 2025.",
    "M. Dahl, V. Magesh, M. Suzgun and D. E. Ho, \"Large legal fictions: Profiling legal hallucinations in large language models,\" Journal of Legal Analysis, vol. 16, no. 1, pp. 64-93, 2024.",
    "P. Liu, D. Stammbach and P. Henderson, \"Who checks the citations? Benchmarking legal hallucination detection,\" arXiv:2606.21155, 2026.",
    "Deepanshu, D. Saxena, D. Rana, A. Varshney and S. R. Laskar, \"NyayaAI: An AI-powered legal assistant using multi-agent architecture and retrieval-augmented generation,\" arXiv:2605.10155, 2026.",
    "V. Vishnuprabha, D. M. Viswanathan, R. Rajesh and A. V. Pillai, \"Augmented question-guided retrieval (AQgR) of Indian case law with LLM, RAG, and structured summaries,\" arXiv:2508.04710, 2025.",
    "M. Hany, M. ElSheraey, M. Said and P. Naoum, \"Inject or navigate? Token-efficient retrieval for LLM analysis of transactional legal documents,\" arXiv:2607.05764, 2026.",
    "J. Bose, \"Falkor-IRAC: Graph-constrained generation for verified legal reasoning in Indian judicial AI,\" arXiv:2605.14665, 2026.",
    "S. Chen, H. Yin and S. Zhou, \"LegalCiteBench: Evaluating citation reliability in legal language models,\" in Proc. ICML, 2026.",
    "V. Ovcharov, \"Citation grounding measures the oracle: Graph coverage determines reported LLM hallucination rates in law,\" arXiv:2606.00898, 2026.",
    "P. Lewis et al., \"Retrieval-augmented generation for knowledge-intensive NLP tasks,\" in Proc. NeurIPS, 2020, pp. 9459-9474.",
    "G. V. Cormack, C. L. A. Clarke and S. Buettcher, \"Reciprocal rank fusion outperforms Condorcet and individual rank learning methods,\" in Proc. ACM SIGIR, 2009, pp. 758-759.",
    "R. Nogueira and K. Cho, \"Passage re-ranking with BERT,\" arXiv:1901.04085, 2019.",
    "S. Xiao, Z. Liu, P. Zhang and N. Muennighoff, \"C-Pack: Packaged resources to advance general Chinese embedding,\" arXiv:2309.07597, 2023.",
    "M. T. Ribeiro, S. Singh and C. Guestrin, \"Why should I trust you? Explaining the predictions of any classifier,\" in Proc. ACM SIGKDD, 2016, pp. 1135-1144.",
    "OpenAI, \"gpt-oss-120b and gpt-oss-20b model card,\" 2025.",
    "LangChain, \"LangGraph: Building stateful, multi-actor applications with LLMs,\" 2025. [Online]. Available: https://langchain-ai.github.io/langgraph/",
    "M. Honnibal, I. Montani, S. Van Landeghem and A. Boyd, \"spaCy: Industrial-strength natural language processing in Python,\" 2020.",
    "A. Joshi et al., \"IL-TUR: Benchmark for Indian legal text understanding and reasoning,\" in Proc. ACL, 2024.",
    "V. Malik et al., \"ILDC for CJPE: Indian legal documents corpus for court judgment prediction and explanation,\" in Proc. ACL-IJCNLP, 2021, pp. 4046-4062.",
    "Indian Supreme Court and High Court judgments, Registry of Open Data on AWS (CC-BY-4.0); India Code, Legislative Department, Government of India.",
]

# Source files shown in the appendix, in order (path, title)
APPENDIX_FILES = [
    ("docketpilot/agents/graph.py", "A.1 Agent graph (LangGraph workflow)"),
    ("docketpilot/privacy/redact.py", "A.2 Privacy gateway (masking)"),
    ("docketpilot/privacy/vault.py", "A.3 Encrypted placeholder vault"),
    ("docketpilot/verification/correct.py", "A.4 Automatic correction of citations"),
    ("docketpilot/retrieval/search.py", "A.5 Hybrid retrieval and re-ranking"),
    ("docketpilot/chat.py", "A.6 Verified research answers"),
]
