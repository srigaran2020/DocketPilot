# Figure captions and how each comparison was made

## fig1a_cost_reduction

**Caption.** Cost reduction against an AI baseline. DocketPilot (measured, gpt-oss-120b on both sides): research answers vs a long-context baseline that reads the full judgments, and case papers vs plain-LLM reading. LegalMind (IEEE Access 2025) vs baseline AI models. NAVINDEX (Hany et al., arXiv:2607.05764, 2026) vs injecting the whole corpus.

**How each comparison was made.**

- **Metric**: cost reduction = 1 - (system's cost / its baseline's cost), each against the baseline its own authors chose.
- **DocketPilot (answers)**: 8 legal research questions across practice areas (bail, divorce, specific performance, limitation, arbitration, maintenance, consumer, motor accident). DocketPilot retrieves 6 reranked judgment passages and up to 5 statute sections, answers, then checks every citation (including AI-judge calls). Every token was counted from Groq's API responses and priced at the list price of gpt-oss-120b (US$0.15 per million input, US$0.60 per million output tokens). Baseline: the same model given the full text of the same judgments and the same statute sections; its input was counted with the o200k tokenizer and its output assumed equal to DocketPilot's answer, which favours the baseline. Result: US$0.00285 vs US$0.02215 per answer.
- **DocketPilot (papers)**: 8 real High Court judgments (AWS Open Data) used as case papers; task: case number, parties and every dated event. DocketPilot reads the case number locally, masks names, and sends one structured call with only the cause title and the sentences containing dates. Baseline: the same model reading the full unmasked text with a generic prompt. Result: US$0.00070 vs US$0.00147 per paper.
- **LegalMind**: published figure (IEEE Access, 2025): an agentic framework built on a fine-tuned DeepSeek R1 with a structured legal dataset, reporting 42.6% cost reduction over baseline AI models. Not re-run by us; the abstract does not give its task set or baseline in detail.
- **NAVINDEX**: published figure (Hany et al., arXiv:2607.05764, 2026): transactional legal documents; the model navigates a compact structured index instead of having the whole document corpus injected into its context on every query. 25% lower dollar cost, with answers judged tied with full injection on all 18 document-bound questions. Same type of baseline as DocketPilot (whole documents in context).

## fig2a_citation_recall

**Caption.** Share of wrong citations caught. Other systems: Liu, Stammbach & Henderson (arXiv:2606.21155, 2026), Table 2, agentic setting, 390 US brief excerpts. DocketPilot: 756 injected fakes on real Indian Supreme Court citations. Same metric, different data. GPT-OSS 120B is the model DocketPilot uses.

**How each comparison was made.**

- **Metric**: recall = share of wrong citations the system flags; precision = share of its flags that really are wrong; F1 = their harmonic mean. Same definitions for every bar.
- **DocketPilot**: 150 real Supreme Court of India cases; 756 wrong citations generated from them (wrong page, wrong year, swapped party names, wrong court, invented case, citation that does not support the stated proposition) mixed with 156 correct citations (seed 13). Each was run through DocketPilot's verifier against its store of 48,168 cases. Recall 99.6%, precision 99.3%.
- **Claude Code, GPT-5, Qwen3.6-27B, GPT-OSS-120B, Gemini 2.5 Flash, Qwen3-8B**: published figures (Liu, Stammbach & Henderson, arXiv:2606.21155, 2026, Table 2): excerpts of US legal briefs with injected citation errors drawn from a taxonomy of 1,000+ real court filings with fabricated citations; 390-example test set. Each model ran as a tool-using agent (up to 30 steps) that can look up case law; Claude Code used its own agent harness. Agentic results shown.
- **Same LLM**: GPT-OSS-120B is the model DocketPilot uses, so the gap between its bar and DocketPilot's shows what the verification pipeline adds over the model alone.
- **Caveat**: same metric, different data: US briefs vs Indian Supreme Court citations; their errors include subtler types.

## fig2b_citation_f1

**Caption.** F1 of citation-error detection; sources as in the recall figure. DocketPilot precision 99.3%.

**How each comparison was made.**

- **Metric**: recall = share of wrong citations the system flags; precision = share of its flags that really are wrong; F1 = their harmonic mean. Same definitions for every bar.
- **DocketPilot**: 150 real Supreme Court of India cases; 756 wrong citations generated from them (wrong page, wrong year, swapped party names, wrong court, invented case, citation that does not support the stated proposition) mixed with 156 correct citations (seed 13). Each was run through DocketPilot's verifier against its store of 48,168 cases. Recall 99.6%, precision 99.3%.
- **Claude Code, GPT-5, Qwen3.6-27B, GPT-OSS-120B, Gemini 2.5 Flash, Qwen3-8B**: published figures (Liu, Stammbach & Henderson, arXiv:2606.21155, 2026, Table 2): excerpts of US legal briefs with injected citation errors drawn from a taxonomy of 1,000+ real court filings with fabricated citations; 390-example test set. Each model ran as a tool-using agent (up to 30 steps) that can look up case law; Claude Code used its own agent harness. Agentic results shown.
- **Same LLM**: GPT-OSS-120B is the model DocketPilot uses, so the gap between its bar and DocketPilot's shows what the verification pipeline adds over the model alone.
- **Caveat**: same metric, different data: US briefs vs Indian Supreme Court citations; their errors include subtler types.

## fig3_hallucination

**Caption.** Citations a lawyer cannot rely on. DocketPilot and the closed-book model: Supreme Court neutral/SCR citations matching no judgment in a store of every SC judgment 1950-2026 (other formats excluded). Lexis+ AI and Westlaw AI-Assisted Research: human-graded hallucination on US law (Magesh et al., 2025). GPT-3.5 and Llama 2: closed-book hallucination on verifiable questions about US federal cases (Dahl et al., 2024). Different protocols and jurisdictions.

**How each comparison was made.**

- **Metric**: share of citations (or answers) a lawyer cannot rely on: fabricated, or not supported by the cited source.
- **DocketPilot**: the same 8 research questions as Fig. 1a; its released answers contained 27 citations. Every citation was checked for existence against a store holding every Supreme Court judgment 1950-2026 (neutral and SCR citations). 0 fabricated.
- **Same LLM, closed book**: gpt-oss-120b asked the same 8 questions and told to cite Indian judgments, with no retrieval; 125 citations, same check. 7 fabricated (5.6%); 63 citations in formats the store does not fully cover (SCC, AIR, High Court reporters) were excluded as uncheckable rather than counted as fabricated.
- **Lexis+ AI, Westlaw AI-Assisted Research**: published figures (Magesh et al., Journal of Empirical Legal Studies, 2025): 200+ preregistered US legal research queries; answers graded by people; a hallucination is an answer that is wrong or cites a source that does not support it. 17% and 33%.
- **GPT-3.5, Llama 2**: published figures (Dahl et al., Journal of Legal Analysis, 2024): closed-book questions with verifiable answers about randomly sampled US federal court cases, checked against court metadata. 69% and 88%.
- **Caveat**: different protocols and jurisdictions; DocketPilot's check is automatic existence checking, the Stanford studies used human grading or ground-truth metadata.

## fig4_cost

**Caption.** Cost of 1,000 research answers at Groq list price for gpt-oss-120b. DocketPilot includes every verification call; the long-context baseline reads the full judgments.

**How each comparison was made.**

- **Metric**: US dollars per 1,000 research answers at Groq list price for gpt-oss-120b.
- **Both bars**: the same 8 questions and token accounting as Fig. 1a; DocketPilot includes every verification call.

