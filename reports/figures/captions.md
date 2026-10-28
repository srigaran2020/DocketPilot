# Figure captions

**fig1a_cost_reduction**: Cost reduction reported by each system against its own baseline. DocketPilot (measured, gpt-oss-120b both sides): research answers vs a long-context baseline that reads the full judgments, and case papers vs plain-LLM reading. LegalMind (IEEE Access 2025) vs baseline AI models. NAVINDEX (Hany et al., arXiv:2607.05764, 2026) vs injecting the whole corpus. Better Call GPT (Martin et al., arXiv:2401.16212, 2024) vs human contract review.

**fig1b_speedup**: Processing time saved. DocketPilot: 8 real High Court judgments vs the same LLM reading them unassisted. LegalMind: vs baseline AI models. Vals Legal AI Report (Feb 2025): legal AI tools 6x faster than lawyers at their slowest (83.3% time saved), up to 80x (98.8%).

**fig2a_citation_recall**: Share of wrong citations caught. Other systems: Liu, Stammbach & Henderson (arXiv:2606.21155, 2026), Table 2, agentic setting, 390 US brief excerpts. DocketPilot: 756 injected fakes on real Indian Supreme Court citations. Same metric, different data. GPT-OSS 120B is the model DocketPilot uses.

**fig2b_citation_f1**: F1 of citation-error detection; sources as in the recall figure. DocketPilot precision 99.3%.

**fig3_hallucination**: Citations a lawyer cannot rely on. DocketPilot and the closed-book model: Supreme Court neutral/SCR citations matching no judgment in a store of every SC judgment 1950-2026 (other formats excluded). Lexis+ AI and Westlaw AI-Assisted Research: human-graded hallucination on US law (Magesh et al., 2025). GPT-3.5 and Llama 2: closed-book hallucination on verifiable questions about US federal cases (Dahl et al., 2024). Different protocols and jurisdictions.

**fig4_cost**: Cost of 1,000 research answers at Groq list price for gpt-oss-120b. DocketPilot includes every verification call; the long-context baseline reads the full judgments.
