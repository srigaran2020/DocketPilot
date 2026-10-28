# DocketPilot compared with LegalMind and other legal AI systems

Our numbers: measured on this build (benchmark run 2026-10-28T15:46:54.753615+00:00). Other systems: copied from their papers. Different datasets and tasks unless the last column says otherwise; do not present a cross-paper difference as a head-to-head result.

## DocketPilot (measured)

| System | Metric | Value | How measured |
|---|---|---|---|
| DocketPilot | Cost reduction vs baseline AI model (research answer) | **87.2%** | gpt-oss-120b on Groq both sides; DocketPilot $0.00285 incl. every verifier call vs long-context baseline $0.02215 per answer |
| DocketPilot | Document processing speed improvement vs baseline AI model | **35.9%** | 3.0s vs 4.7s per real High Court judgment, same model, fresh rate-limit window per run |
| DocketPilot | Document processing cost reduction | **52.1%** | same documents as above |
| DocketPilot | Case number read correctly (real HC judgments) | **87.5%** | baseline model 88% |
| DocketPilot | Fabricated citations in answers | **0.0%** | 0 of 27 citations; 0 outside the store's coverage (not counted) |
| Same model, no DocketPilot | Fabricated citations in answers | **5.6%** | 7 of 125 citations; 63 outside the store's coverage (not counted) |
| DocketPilot | Recall of citation errors (fake-citation benchmark) | **99.6%** | 756 injected fakes, 156 real citations; precision 99.3% |
| DocketPilot | F1 of citation-error detection | **99.5%** | same benchmark |
| DocketPilot | Personal data hidden from the AI (held-out recall) | **96.8%** | synthetic Indian PII |
| DocketPilot | Retrieval Recall@5 (hybrid + rerank) | **95.7%** | headnote -> own judgment, s.138 SC |

## Published results of other systems

| System | Metric | Value | Source | Comparable? |
|---|---|---|---|---|
| LegalMind (DeepSeek R1, agentic) | Cost reduction vs baseline AI models | 42.6% | LegalMind, IEEE Access 2025, DOI 10.1109/ACCESS.2025.3586781, abstract | Same metric name; their baseline and tasks are not public in the abstract. |
| LegalMind (DeepSeek R1, agentic) | Document processing speed improvement vs baseline AI models | 60.8% | DOI 10.1109/ACCESS.2025.3586781 (IEEE Access, 2025), abstract | Same metric name; their documents and baseline are not public in the abstract. |
| NAVEMBED (Hany et al., 2026) | Cost reduction vs whole-corpus injection | 67.5% | arXiv:2607.05764, RUN-005: US$0.611 vs US$1.881 | Same baseline type as DocketPilot (full documents in context). |
| NAVINDEX (Hany et al., 2026) | Cost reduction vs whole-corpus injection | 25% | arXiv:2607.05764: US$1.21 vs US$1.61 | Same baseline type as DocketPilot. |
| Lexis+ AI | Hallucination rate (legal research answers) | 17% | Magesh et al., 'Hallucination-Free?', arXiv:2405.20362 (Stanford RegLab/HAI); figures as reported by LawSites, June 2024 | US law, 200+ preregistered queries, human-graded; ours is an automatic existence check on Indian law. |
| Westlaw AI-Assisted Research | Hallucination rate (legal research answers) | 33% | Magesh et al., arXiv:2405.20362; LawSites, June 2024 | As above. |
| Lexis+ AI | Accurate answers | 65% | Magesh et al., arXiv:2405.20362; LawSites, June 2024 | Human-graded accuracy; not measured for DocketPilot. |
| Westlaw AI-Assisted Research | Accurate answers | 42% | Magesh et al., arXiv:2405.20362; LawSites, June 2024 | As above. |
| Ask Practical Law AI | Accurate answers | 20% | Magesh et al., J. Empirical Legal Studies 22 (2025), DOI 10.1111/jels.12413 (text: 19% -> 20% after re-grading) | Human-graded accuracy; not measured for DocketPilot. |
| GPT-3.5 (closed book) | Hallucination rate (legal queries) | 69% | Dahl, Magesh, Suzgun & Ho, 'Large Legal Fictions', J. Legal Analysis 16 (2024), arXiv:2401.01301 | Closed-book model on verifiable questions about US federal cases; like our closed-book baseline, other law. |
| Llama 2 (closed book) | Hallucination rate (legal queries) | 88% | Dahl et al. 2024, arXiv:2401.01301 | As above. |
| Harvey Assistant | Document Q&A score (lawyer baseline 70.1) | 94.8% | Vals Legal AI Report (VLAIR), 27 Feb 2025 | Task accuracy vs lawyers; not a DocketPilot metric. |
| CoCounsel | Document Q&A score (lawyer baseline 70.1) | 89.6% | Vals Legal AI Report (VLAIR), 27 Feb 2025 | As above. |
| GPT-5, agentic citation checker | Recall of citation errors (hallucination detection) | 84.4% | Liu, Stammbach & Henderson, 'Who Checks the Citations?', arXiv:2606.21155 (2026) | Same metric (share of bad citations caught); their 1,300 US brief excerpts are harder and more varied than our fakes. |
| GPT-5, agentic citation checker | F1 of citation-error detection | 55.0% | arXiv:2606.21155 | Same metric; different data (see above). |
| Best of 21 LLMs, closed book | Citation retrieval/completion score | 7/100 (below) | Chen, Yin & Zhou, 'LegalCiteBench', arXiv:2605.10186 (ICML 2026) | Shows why closed-book models cannot be trusted with citations; misleading-answer rate >94% for 20 of 21 models. |
| 4 commercial LLMs (Ukrainian law) | Hallucinated citations, sparse vs dense reference store | 15-21 vs ~0.1-1.1% | Ovcharov, 'Citation Grounding Measures the Oracle', arXiv:2606.00898 (2026) | Methodological: the measured rate depends on the reference store's coverage. We therefore count only formats our store covers completely as fabricated. |
| Falkor-IRAC (Indian judicial AI) | Verified answers via graph verifier | qualitative | Bose, arXiv:2605.14665 (2026); proof of concept on 51 SC judgments | Closest Indian system; reports no hallucination or retrieval metric to compare. |

## How to read this

- **Same metric as LegalMind**: cost reduction and document-processing speed improvement over a baseline AI model. Our baseline is the same LLM without DocketPilot's pipeline, so the gain comes from the system design.
- **Hallucination**: Stanford's figures are human-graded answer errors on US law; ours count citations that match no real judgment. Both are 'citations a lawyer cannot rely on', but the protocols differ.
- **Citation-error detection**: same definition as Liu et al. (recall/F1 of bad citations caught); our fakes are simpler (wrong page/year/court, swapped names, invented cases, wrong proposition).
- Re-run: `python -m docketpilot.evaluation.benchmark_vs` then `python -m docketpilot.evaluation.comparison`.
