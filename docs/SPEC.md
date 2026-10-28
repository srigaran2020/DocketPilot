# DocketPilot — Technical Specification and Build Guide

**Project:** DocketPilot — an agentic AI system for Indian legal research, drafting, citation verification and case management
**Team:** Srigaran N, Selvaraj Vasanthakumar, Suryaprakash P (Batch 20, CSE-AIML) · Supervisor: Dr. Saravanan R
**Pilot domain:** Cheque dishonour cases under Section 138, Negotiable Instruments Act, 1881
**Document status:** v1.0, written 27 Oct 2026. This replaces the technical choices in the Phase 1 deck where they differ (see Section 2).

---

## 0. How to use this document with Claude Code

1. Put this file in the repo root as `docs/SPEC.md`. Also create a short `CLAUDE.md` that says: "Read docs/SPEC.md first. Follow Section 18 (working agreements). Work one phase at a time."
2. Ask Claude Code to build **one phase at a time** (Section 17). Each phase has acceptance criteria. Do not move on until they pass.
3. Start with **Phase 0 (data discovery)**. Several choices in this spec depend on what the open datasets really contain. Claude Code must inspect the data and report back before locking the schema.
4. This document has no code on purpose. It tells Claude Code *what* to build and *why*. Claude Code decides the code.

---

## 1. Product summary

### 1.1 The problem
Indian courts and the Bar have seen lawyers file AI-generated citations that do not exist. Existing legal AI tools produce fluent text with no proof behind it. A lawyer cannot safely use them.

### 1.2 What DocketPilot does
A lawyer uploads case documents (FIR, cheque, return memo, notice, contracts, scanned PDFs, or a voice note). DocketPilot:
1. Removes confidential details **on the lawyer's own machine/server** before any AI model sees the text.
2. Researches the right law and precedents.
3. Drafts a ready-to-file document (.docx/PDF) from a fixed court-style template.
4. **Independently verifies every citation, quote and statute reference** and marks each one green / amber / red, with the source passage shown.
5. Shows strengths, weaknesses and similar past cases.
6. Creates deadlines and reminders, and keeps everything on a long-term case dashboard.

### 1.3 The one promise
**No citation reaches the lawyer unchecked.** Every citation shows its status and its evidence. The system never claims a case is "fake" — it says "verified", "partly matched", or "not found in our corpus", and the lawyer decides.

### 1.4 What it is NOT
- Not a legal advisor. It does not predict who will win. It supports a lawyer, who signs off.
- Not for the general public. Target user is a practising advocate or a small law firm.

---

## 2. Changes from the Phase 1 deck

| Deck says | Problem | New decision |
|---|---|---|
| Indian Kanoon API as main source | Paid. Scraping the website breaks its terms. | **Free open data**: Supreme Court and High Court judgments on AWS Open Data (CC-BY-4.0), statutes from India Code, plus Gazette PDFs. See Section 5. |
| Only dense vectors in ChromaDB | Legal search needs exact words (section numbers, party names, citations). Dense-only misses them. Chroma is weak at hybrid search and scale. | **Hybrid retrieval**: lexical (BM25) + dense + sparse, fused, then reranked. Vector store: **Qdrant**. Plus **exact-lookup indexes** in PostgreSQL. |
| "TF-IDF if required" | Good instinct. | TF-IDF/BM25 is used in four places (Section 6.4), and as a baseline in the paper. |
| Groq-hosted LLM only (the deck's LLaMA is replaced by **openai/gpt-oss-120b on Groq**) | Free tier has rate limits and can change. Single point of failure. | **LLM provider abstraction**: `openai/gpt-oss-120b` on Groq as the primary model (redacted text only), with automatic fallback to a smaller local model. |
| Verification described as an agent | If an LLM does all the checking, it can hallucinate the check. | Verification is **mostly deterministic** (database lookups, string matching). An LLM is used only for one narrow step, with evidence shown. |
| Seven agents, all LLM-style | Slow, costly, hard to test. | Keep seven named agents but use plain code wherever a model is not needed (Section 7). |

---

## 3. Design principles (Claude Code must follow these)

1. **Verifiable over fluent.** Anything legal shown to the user must link to a stored source passage.
2. **Deterministic first, LLM second.** Use exact lookups, rules and indexes before a model. An LLM only does what code cannot (reading, drafting, judging support).
3. **Privacy by default.** Raw confidential text never leaves the local environment. Only redacted text may go to an external model.
4. **Human in the loop.** The lawyer must approve before a draft is finalised. The workflow pauses for that approval.
5. **Say "I don't know."** "Not found in corpus" is a valid, honest answer. Never fill the gap with a guess.
6. **Rules as data.** Limitation periods, amendment dates, document templates and section mappings live in versioned data files with a legal source for each, not buried in code.
7. **Measure everything.** Every claim in the paper must come from an automated evaluation that can be re-run.
8. **No paid services.** Everything must run on free, open-source or free-tier components, and keep working if a free tier disappears.

---

## 4. System architecture

Six layers, from bottom to top.

**Layer 1 — Knowledge base (offline, built once and refreshed)**
Downloads open legal data, parses it, cleans it, and builds the indexes in Layer 2.

**Layer 2 — Indexes and stores**
- PostgreSQL: cases, citations, citation graph, statute versions, users, matters, reminders, audit log, LangGraph checkpoints.
- Qdrant: dense + sparse vectors for judgment chunks and statute sections.
- A lexical (BM25) index. Preferred: PostgreSQL full-text search for the start; move to OpenSearch only if measurements show a need.
- Object storage (MinIO, S3-compatible): original uploads, generated drafts, raw judgment files.
- Redis: cache, job queue, rate-limit counters.

**Layer 3 — Privacy gateway**
Everything from a lawyer passes through OCR/transcription → PII detection → redaction → local vault. Only after this can text go to an external LLM.

**Layer 4 — Agent graph (LangGraph)**
Seven agents (Section 7) as a stateful graph with saved state and a human approval pause.

**Layer 5 — Services (FastAPI)**
Stateless API, background workers, scheduler for reminders and amendment checks.

**Layer 6 — Web app (React)**
Case dashboard, research workspace, draft editor with citation badges, verification report, upload and redaction preview, reminders calendar, audit view.

### Main request flow (draft a Section 138 complaint)
1. Lawyer uploads documents to a matter.
2. Layer 3 extracts text, redacts PII, stores the mapping in the local vault.
3. Document Analysis agent extracts structured facts (dates, amounts, cheque number, bank, notice dates).
4. Orchestrator builds a plan; Research agent retrieves statute text valid on the relevant date and top precedents.
5. Reasoning agent fills the draft template using only retrieved material.
6. Verification agent checks every citation, quote and statute reference (Section 8).
7. Strategy & Risk agent produces the element checklist and similar-case list.
8. Workflow **pauses**. Lawyer reviews draft + verification report and approves or edits.
9. System re-inserts the real names (from the vault) and produces the .docx/PDF.
10. Monitoring agent creates reminders and updates the dashboard.

---

## 5. Data sources and knowledge base

### 5.1 Sources (all free)

| Source | Use | Notes |
|---|---|---|
| **Indian Supreme Court Judgments** — AWS Open Data, bucket `indian-supreme-court-judgments` (ap-south-1) | Core precedent corpus | Coverage 1950–2025, CC-BY-4.0, bi-monthly updates. Judgments as zip files; metadata in JSON and Parquet. Listable without an AWS account. |
| **Indian High Court Judgments** — AWS Open Data, bucket `indian-high-court-judgments` (ap-south-1), maintained by Dattam Labs | Precedents from 25 High Courts | CC-BY-4.0, quarterly updates. Individual PDFs plus tar files; metadata in JSON and Parquet. Very large, so ingest a **filtered subset**. |
| **India Code** (indiacode.nic.in) | Statute text (Acts, sections) | Official. Parse Act PDFs/pages into section-level records. |
| **Gazette of India** (egazette.gov.in) | Amendment notifications | Used for the amendment ledger. Parsing is hard; start with a curated list. |
| **Bare-Act mapping tables** (IPC↔BNS, CrPC↔BNSS, IEA↔BSA) | Handles the 1 July 2024 criminal-law change | Build from India Code and official concordance documents; check by hand. |
| **Research datasets**: IL-TUR benchmark (ACL 2024) and other Indian legal datasets (FIRE AILA, OpenNyAI, ILDC — **check availability and licence before use**) | Evaluation only | Do not mix evaluation data into the index without tracking it. |

Provenance rule: every record stores its source, download date, licence and a content hash.

### 5.2 Pilot corpus scope
- All Supreme Court judgments that mention the Negotiable Instruments Act or Section 138 (and a wider SC set for citation resolution).
- High Court judgments on Section 138 from a chosen set of courts (suggest 3–5 courts, last ~10 years), subject to what Phase 0 finds.
- Statutes: NI Act in full, plus the Acts it commonly touches (BNS/IPC, BNSS/CrPC, Bharatiya Sakshya Adhiniyam/Evidence Act, Limitation Act, Civil Procedure Code where relevant).

### 5.3 Parsing and structuring judgments
- Use the text layer if the PDF has one. Use OCR only as a fallback, and record which was used and the OCR confidence.
- Clean headers, footers and page numbers.
- Split each judgment into sections by **rhetorical role**: facts, issues, arguments, reasoning, holding, order. Start with rule-based heading detection; consider a small model later.
- Extract structured fields: court, bench, date, parties, case number, neutral citation, statutes cited, cases cited, outcome.
- **Outcome extraction** (allowed / dismissed / acquitted / convicted / compounded / remanded): rules first, LLM-assisted second, each with a confidence score. Low-confidence outcomes are marked "unknown", not guessed.

### 5.4 Citation graph (a key asset)
- Detect every citation inside every judgment and link it to the cited case when it can be resolved.
- Store edges: *case A cites case B*, with the sentence and the signal words around it ("followed", "relied upon", "distinguished", "overruled", "per incuriam").
- This graph powers: citation resolution, "is it still good law" signals, similar-case ranking and the verification agent.
- **Alias table**: older reporter citations (SCC, AIR, Cr LJ, etc.) are usually not in the open metadata. Mine them from how judgments cite each other (party names + year + reporter string appearing together) to build a mapping from reporter citation to case. Store a confidence for each alias.
- Do **not** copy publisher headnotes or content from paid reporters. Those are copyrighted. Use judgment text only.

### 5.5 Statute store with date validity
- One record per **section version**: Act, section, text, `valid_from`, `valid_to`, amending Act/notification, source URL, hash.
- Query form: "give me Section X of Act Y **as on date D**".
- Maintain an **amendment ledger** (a versioned data file). Seed it by hand for the pilot Acts and cross-check against India Code. For the NI Act, the ledger must at least cover the 2002, 2015 and 2018 amendments (including the added Sections 143A and 148) — Claude Code must confirm dates and text against India Code and not rely on this document.
- Special handling for the IPC→BNS switch: an offence committed before 1 July 2024 is generally under the old code, after under the new. The Research agent must pick based on the offence date and show both when unsure.

---

## 6. Retrieval design (fast and scalable)

### 6.1 Tiered retrieval — use the cheapest method that works

| Tier | Query type | Method | Target latency (p95) |
|---|---|---|---|
| 1 | Exact citation, case number, neutral citation | Hash/B-tree lookup in PostgreSQL | < 50 ms |
| 2 | Statute section "as on date" | Indexed lookup on section versions | < 50 ms |
| 3 | Keyword / phrase / party name | BM25 lexical search | < 150 ms |
| 4 | Concept / facts-based question | Hybrid: BM25 + dense + sparse, fused (reciprocal rank fusion) | < 500 ms |
| 5 | Final ranking | Cross-encoder reranker on the top ~50 → top 10 | < 1.5 s extra |

Targets apply to the pilot corpus and must be measured, not assumed. The design must still scale to millions of chunks by configuration, not by rewrite.

### 6.2 Models (all free, runnable locally)
- **Embeddings:** BGE-M3 as the default. It is multilingual and produces dense and sparse vectors from one model. Benchmark against multilingual-e5 and an Indian-legal BERT (such as InLegalBERT) in the evaluation. Choose by measured results.
- **Reranker:** a BGE multilingual cross-encoder reranker. Benchmark with and without.
- **Language:** English first. Hindi/Tamil queries are a stretch goal handled by the multilingual embedder and translation.

### 6.3 Index design
- **Chunking:** by judgment section (Section 5.3), with small "child" chunks for matching and a larger "parent" passage returned for context. Keep chunk → case → page offsets so a citation badge can open the exact passage.
- **Filters stored with each vector:** court, year, bench strength, statutes cited, outcome, matter type. Filtering happens inside the vector search, not after.
- **Vector storage:** use quantisation to cut memory. Tune HNSW settings using the evaluation set, not defaults.
- **Statutes:** index each section as its own record; keep separate from judgments.

### 6.4 Where TF-IDF / BM25 is used
1. **BM25 as the lexical leg** of hybrid search (BM25 is the stronger modern form of TF-IDF).
2. **Near-duplicate detection** of judgments (same judgment appearing in several courts' feeds or formats) with TF-IDF cosine similarity.
3. **Fast fallback** when the embedding service is down or for very short keyword queries.
4. **A baseline in the paper** to show what hybrid and reranking add.

### 6.5 Scalability and speed measures
- Stateless API behind a load balancer; scale workers separately from the API.
- Ingestion and embedding run as background jobs on a queue. Re-runs only touch changed documents (use content hashes).
- Cache: query results, embeddings of repeated queries, statute lookups. Invalidate on corpus refresh.
- Run the one-time bulk embedding as a resumable batch job; query-time embedding of short queries is a separate, lightweight path.
- Docker Compose for development. Provide Kubernetes manifests as a stretch goal.
- Load test with Locust or k6; publish p50/p95/p99 and throughput.

---

## 7. The seven agents

Principle: each agent has typed inputs and outputs (structured, validated) and its own tests. "LLM?" shows whether a model is needed.

| # | Agent | Job | LLM? |
|---|---|---|---|
| 1 | **Orchestrator** | Reads the lawyer's request, chooses the workflow (research only / draft / analyse case), manages the shared state and the approval pause. | Light (intent routing); rules for the rest |
| 2 | **Document Analysis** | OCR/transcript → structured facts (parties, dates, amounts, cheque details, notice dates, bank memo reason). Facts carry the page/line they came from. | Yes, with schema-validated output |
| 3 | **Research** | Runs tiered retrieval; returns statute text valid on the date and ranked precedents with passages. Never writes legal conclusions. | Retrieval is code; only query rewriting uses an LLM |
| 4 | **Reasoning / Drafting** | Fills the court-style template. Fixed boilerplate comes from the template; the LLM writes only designated sections, using only retrieved passages, and must attach a passage ID to every legal statement. | Yes |
| 5 | **Verification** | The core agent (Section 8). Checks every citation, quote and statute reference. Cannot be bypassed. | Mostly **no**; one narrow LLM step |
| 6 | **Strategy & Risk** | Element-by-element checklist for Section 138, weaknesses, and similar past cases with outcomes. | Light; mostly rules + retrieval |
| 7 | **Monitoring** | Scheduled jobs: deadline reminders, amendment watch, re-verification of old drafts when law changes. | No |

**Orchestration requirements (LangGraph):**
- Typed state schema; state saved to PostgreSQL after every step so a crashed or paused job resumes.
- A real **human-approval interrupt** before finalising any draft.
- Timeouts, retries with backoff, and a clear failure state per agent. If Verification fails or is unavailable, the draft **cannot** be released.
- Every step is traced (inputs, outputs, latency, model used, token count).

---

## 8. Citation verification — the core of the project

Run on every citation in a draft, in this order.

**Step 1 — Extract.** Find every (legal proposition, citation) pair, every direct quote, and every statute reference in the draft.

**Step 2 — Normalise.** Convert each citation to a canonical form. Support at least: neutral citations (e.g. "2023 INSC 123"), SCC, AIR, SCC OnLine, Cr LJ, and "Party v. Party (year)". Keep the original string for display.

**Step 3 — Resolve.** Look up in the local case index: exact canonical key first, then alias table, then fuzzy match on party names + year + court. Return the best candidates with scores.

**Step 4 — Existence verdict.** Assign one of:
- **VERIFIED** — resolved with high confidence.
- **PARTIAL** — matched, but a detail differs (wrong year, wrong page, wrong court).
- **NOT FOUND IN CORPUS** — no match. This does **not** prove it is fake; the open corpus has limits. The UI says exactly that.
- **CONFLICT** — the citation points to a different case than the one named.

**Step 5 — Quote check.** For each direct quote, search the resolved judgment's text for it (after normalising whitespace and punctuation). Report exact, near-exact (with the differences shown) or not found.

**Step 6 — Proposition check.** Take the passages of the cited case that best match the proposition. Ask an LLM acting as a strict judge: does this passage **support**, **partly support**, **not support** or **contradict** the proposition? The judge must return its answer in a fixed format and **quote the passage text it relied on**. If it cannot quote one, the result is "unsupported". Use a *different* model or prompt from the drafting step. Show the passage to the lawyer.

**Step 7 — Good-law signal.** From the citation graph, show whether later cases cite it as overruled, distinguished or doubted. Label it a **signal**, not a legal conclusion.

**Step 8 — Statute check.** For each section reference: does it exist, is the quoted text identical to the stored version, and was that version in force on the relevant date? Flag references to repealed provisions (for example, IPC sections for post-July-2024 offences).

**Step 9 — Gate and report.** Produce a verification report per draft. Rules:
- Any citation that is CONFLICT, or any quote that is not found, **blocks release** until the lawyer resolves it.
- NOT FOUND and PARTIAL are shown in amber with a required acknowledgement.
- Only fully green items pass silently.
- The report is saved with the draft and the audit log.

**Why this design works:** Steps 1–5 and 7–8 are plain lookups and string matching, so they cannot hallucinate. The only model step (Step 6) is forced to show its evidence.

---

## 9. Section 138 pilot: legal logic as data

Store these as versioned data files with the legal source next to each item. **Claude Code must not hard-code them, and the team must have a qualified lawyer or the supervisor confirm them before use.**

**Element checklist** (the Strategy & Risk agent maps case facts to each, showing evidence and a status of satisfied / unclear / missing):
1. A cheque was drawn for discharge, in whole or part, of a legally enforceable debt or liability.
2. Cheque presented within its validity period.
3. Cheque returned unpaid (insufficient funds or arrangement exceeded, etc.).
4. Written demand notice sent to the drawer within the statutory period after the return memo.
5. Drawer failed to pay within the statutory period after receiving notice.
6. Complaint filed within the statutory period after the cause of action arises.
7. Court has territorial jurisdiction.

**Deadline rules** (the Monitoring agent turns these into dated reminders, with a warning ahead of each deadline): cheque validity, notice period, payment period, complaint period. The rule engine must store the legal source and the date the rule was last confirmed. Provide a way to record court holidays and the lawyer's own override.

**Related provisions to include in retrieval:** summary trial, interim compensation, compensation on appeal, compounding, and the 2015 jurisdiction change — verify each against India Code.

---

## 10. Privacy and security

### 10.1 Redaction pipeline
- **Detect:** rule-based recognisers for Indian identifiers (Aadhaar with checksum validation, PAN, phone, email, bank account and IFSC, vehicle numbers, addresses) plus a named-entity model for names, organisations and places. Use Microsoft Presidio's framework with custom Indian recognisers as a starting point.
- **Replace** each entity with a consistent placeholder (e.g. "PERSON_1"), so the model still understands who is who.
- **Vault:** the placeholder→real value map is stored locally, encrypted, per matter. It is never sent to any external service and never logged.
- **Restore** real values only after the lawyer approves the draft, when generating the final file.
- **Preview:** the lawyer can see exactly what was masked and correct mistakes (add missed items, un-mask false hits) before anything leaves the machine.
- **Local-only mode:** a setting that forces all models to run locally (nothing leaves the machine), for highly sensitive matters.
- **Measure it:** build a synthetic Indian-PII test set. Report precision, recall and the **leakage rate** (share of sensitive items that still reach the external model). Recall matters more than precision here.

### 10.2 Enterprise-grade controls
- Login, roles (advocate, junior, admin) and per-matter access control. Row-level security so one firm can never see another firm's data.
- Encryption in transit; encryption at rest for the database, object storage and vault.
- **Audit log** (append-only): who viewed, uploaded, generated, approved or exported what, and which model saw what (redacted) text.
- No personal data in application logs or traces. Secrets only in environment/secret stores.
- Retention and deletion controls per matter. Design with the **Digital Personal Data Protection Act, 2023** in mind and note which parts apply.
- Backups with a tested restore.
- Dependency and container scanning in CI.

---

## 11. Case management, reminders and dashboard

- **Matter record:** parties, court, case number, stage, documents, drafts (versioned), verification reports, notes, timeline.
- **Dashboard:** upcoming deadlines and hearings, matters needing action, drafts awaiting approval, citations needing attention, and amendment alerts affecting open matters.
- **Reminders:** created from the rule engine and from dates in documents (hearing dates, notice dates). Delivery by in-app notification and email (free SMTP), plus a downloadable calendar (.ics) file. No paid messaging.
- **Amendment watch:** a scheduled job checks free official sources for new amendments to the pilot Acts and flags open matters that might be affected. Respect each site's terms and rate limits. Provide a manual "upload an amendment" path as a fallback.
- **Persistence:** LangGraph checkpoints and all matter data live in PostgreSQL, so work continues across sessions.

---

## 12. Document and voice ingestion

- **PDF/images:** use the embedded text first; OCR fallback with Tesseract (English plus Hindi and Tamil language packs). Evaluate PaddleOCR or docTR as alternatives on a small sample of real-looking scans. Store the OCR confidence per page and show low-confidence pages to the lawyer for checking.
- **Layout:** keep page numbers and line positions so every extracted fact can point back to its source.
- **Voice:** local speech-to-text (faster-whisper; consider an Indian-language model for regional languages). Transcripts go through the same redaction pipeline.
- **Limits to state in the UI:** handwriting and very poor scans may fail; the lawyer must check low-confidence pages.

---

## 13. Output documents

- Use **court-style templates** (Word format) for: statutory demand notice (Section 138), criminal complaint, reply to notice, and affidavit. Start with these four.
- The template holds the fixed legal wording. The LLM fills only marked sections (facts, grounds, prayer) using extracted facts and retrieved passages.
- Final output as .docx and PDF. Citations in the final file include verified full citations.
- Every generated file embeds a short verification summary (as an appendix page that the lawyer can remove).

---

## 14. Technology stack (final)

| Area | Choice | Reason / alternative |
|---|---|---|
| Language | Python 3.11+ | |
| API | FastAPI (async) | |
| Orchestration | LangGraph with PostgreSQL checkpointer | Resume, pause for approval |
| Relational + lexical | PostgreSQL (with full-text search and trigram matching) | One database for many jobs |
| Vector store | Qdrant (self-hosted) | Hybrid dense+sparse, filtering, quantisation. Alternative: PostgreSQL pgvector if the team wants fewer services |
| Cache / queue | Redis with a task queue (Celery or Arq) | |
| Object storage | MinIO | S3-compatible, free |
| Embeddings / reranker | BGE-M3 and a BGE reranker (benchmarked against alternatives) | Run locally |
| LLM | Provider-agnostic. **Primary: `openai/gpt-oss-120b` on Groq free tier** (redacted text only). Fallback: a smaller local model served with Ollama. Suggested first choice: `gpt-oss-20b` (same family, so prompts and output format transfer), otherwise a quantised Qwen or Llama in the ~7–8B class. The fallback will be weaker than the 120B model; the UI must say when it is in use | Check current Groq free-tier limits (requests and tokens per minute/day); never depend on them. Keep model name in configuration |
| LLM roles | Drafting and fact extraction use the primary model. The verification judge (Section 8, Step 6) should use a **different model or a different prompt/setting** from drafting, for example the local or a second Groq model, so the drafter does not grade itself | Evaluate which pairing works best |
| LLM output handling | gpt-oss is a reasoning model. Use structured (schema-validated) outputs, set the reasoning effort per task (low for extraction, higher for drafting and judging), and never store or show the model's hidden reasoning as evidence. Evidence is always a quoted source passage | Verify current Groq API parameters in the docs during Phase 1 |
| OCR / speech | Tesseract (+ PaddleOCR/docTR trial); faster-whisper | |
| PII | Presidio + custom Indian recognisers + NER model | |
| Documents out | Template-based Word generation; PDF conversion | |
| Frontend | React (TypeScript) | |
| Observability | OpenTelemetry + self-hosted Langfuse (or similar) for LLM tracing | Free, self-hosted |
| Quality | pytest, type checks, linting, pre-commit, GitHub Actions CI | |
| Packaging | Docker and Docker Compose | |

---

## 15. Non-functional targets (measure and report)

| Quality | Target |
|---|---|
| Exact citation / statute lookup | p95 < 50 ms |
| Hybrid search, top 10 | p95 < 500 ms (pilot corpus) |
| Verification of a 20-citation draft | < 20 s |
| End-to-end draft with progress shown | < 2 min typical |
| Citation fake-detection | Recall ≥ 95% on the benchmark (Section 16.2), with the false-alarm rate reported |
| PII leakage to external model | < 1% of sensitive items on the test set |
| Availability of core flow when the external LLM is down | Falls back to local model, with a clear notice |
| Test coverage | ≥ 80% on verification, redaction, statute and rule-engine modules |

These are goals. If real results are lower, report the real numbers; do not tune the test to hit the target.

---

## 16. Evaluation plan (also the backbone of the research paper)

### 16.1 Retrieval
- Build a gold set of ~100–200 queries with relevant statutes and precedents (use public benchmark data such as IL-TUR/AILA where licences permit, plus a hand-labelled Section 138 set checked by a lawyer).
- Compare: TF-IDF → BM25 → dense only → hybrid → hybrid + reranker. Metrics: Recall@k, MRR, nDCG, and latency.
- Compare embedding models (BGE-M3, multilingual-e5, an Indian-legal BERT).

### 16.2 Citation verification (main contribution)
- **Build a fake-citation benchmark.** Take real citations from judgments (true positives). Create fakes by controlled changes: wrong volume/page, wrong year, swapped party names, wrong court, fully invented case, and real case attached to a wrong proposition. Label each by type.
- Report per-type precision, recall and F1.
- Baselines: (a) plain LLM drafting with no verification; (b) LLM self-check; (c) DocketPilot.
- Measure the hallucination rate of drafts with and without the verifier.

### 16.3 Statute accuracy
- Test "as on date" queries across amendment boundaries (before/after each amendment, before/after 1 July 2024). Report exact-match accuracy.

### 16.4 Privacy
- Precision, recall and leakage rate on the synthetic Indian-PII set, with and without the lawyer preview step.

### 16.5 Strategy & Risk
- Check the element checklist against hand-labelled cases. Check outcome extraction accuracy. Do not report "prediction accuracy"; report retrieval quality of similar cases and checklist agreement.

### 16.6 System
- Load tests, latency percentiles, cost (should be zero), and a small **user study** with a few advocates or law students: time saved, trust, and errors caught.

### 16.7 Paper positioning
Contributions to claim, only if the results support them: (1) open-data citation verification for Indian law with an honest "not found" state; (2) a fake-citation benchmark for Indian law; (3) date-aware statute versioning including the BNS/BNSS transition; (4) measured privacy-first redaction; (5) element-based risk analysis for Section 138. Read related work first, including recent Indian-law RAG papers (for example, "Domain-Partitioned Hybrid RAG for Legal Reasoning: Toward Modular and Explainable Legal AI for India", arXiv 2602.23371) and Neethi AI, and state clearly how DocketPilot differs.

---

## 17. Build phases and acceptance criteria

Suggested split for three people: **A) Data and retrieval**, **B) Agents and verification**, **C) App, privacy and operations**. Dates are indicative; the quality bar matters more than the calendar.

**Phase 0 — Discovery (about 1 week)**
- Inspect the SC and HC datasets: schema, text quality, share of scanned files, which courts and years exist, how many Section 138 cases.
- Report the findings and a proposed pilot corpus. Confirm the final database schema.
- *Accept when:* a written data report exists, the pilot corpus is chosen, and the schema is agreed.

**Phase 1 — Foundations**
- Repo, Docker Compose environment, CI, configuration, secrets handling, database migrations, authentication skeleton, audit log.
- *Accept when:* one command starts the full stack and CI runs tests green.

**Phase 2 — Knowledge base**
- Ingestion pipeline for judgments and statutes; parsing; structure extraction; citation detection; citation graph and alias table; statute versioning and amendment ledger for the NI Act family.
- *Accept when:* pilot corpus is loaded with provenance; ≥ 95% of sampled judgments parse correctly by hand-check; "NI Act Section 138 as on date X" returns the correct version across all amendment boundaries.

**Phase 3 — Retrieval**
- Tiered retrieval, hybrid search, reranker, caching, retrieval API.
- *Accept when:* the retrieval evaluation (16.1) runs automatically and the latency targets in Section 15 are met or honestly reported.

**Phase 4 — Privacy gateway and ingestion of user documents**
- OCR, voice transcription, redaction, vault, preview.
- *Accept when:* leakage rate on the PII test set is measured and below target, and the lawyer can review and correct masking.

**Phase 5 — Verification engine**
- All steps in Section 8, as a standalone service first (usable without the agents).
- *Accept when:* the fake-citation benchmark (16.2) runs automatically; results reported per fake type.

**Phase 6 — Agent graph and drafting**
- All seven agents in LangGraph, templates, approval pause, draft generation, strategy & risk checklist, reminders.
- *Accept when:* a complete Section 138 matter goes from uploaded documents to an approved, verified .docx/PDF with reminders, and a failed verification correctly blocks release.

**Phase 7 — Web app**
- Dashboard, research workspace, draft editor with citation badges and source-passage viewer, verification report view, redaction preview, reminders calendar, admin/audit.
- *Accept when:* the full flow works in the browser, and a non-team user can complete it with no help.

**Phase 8 — Hardening and evaluation**
- Load tests, security review, backup/restore drill, full evaluation run, user study, documentation (user guide, admin guide, API docs, architecture, model card, limitations).
- *Accept when:* the complete evaluation report is generated by one command and all numbers in the paper trace to it.

---

## 18. Working agreements for Claude Code

1. **Read this spec first.** If something here seems wrong or unclear, stop and ask. Do not silently change the design.
2. **One phase at a time.** Plan the phase, list the tasks, build, test, then report against the acceptance criteria.
3. **Tests with every module.** Verification, redaction, statute lookup and the rule engine need thorough tests, including nasty cases (bad OCR, similar party names, repealed sections, dates on amendment boundaries).
4. **Never invent legal facts.** Statutes, limitation periods, amendment dates and section numbers must come from the stored sources or from data files the team has confirmed. If unsure, mark as "needs lawyer confirmation".
5. **No real personal data in the repo, logs, tests or prompts.** Use synthetic data only.
6. **No paid or non-free dependencies.** If a free tier is used, put it behind an interface with a local fallback.
7. **Configuration over hard-coding.** Models, thresholds, court lists, rules and templates are configurable.
8. **Everything reproducible.** Pin dependency versions. Record dataset versions, model versions and prompt versions with each evaluation run.
9. **Prompts are versioned files**, with tests where possible.
10. **Document as you go:** a short README per module, architecture notes, and a decision log explaining each choice and what was rejected.
11. **Small, clear commits** per task, with messages that say what and why.
12. **Respect source terms:** follow licences (keep CC-BY attribution) and robots/terms of official sites; rate-limit any downloads.
13. **Report honestly.** If a metric misses its target, say so and explain; do not adjust the test to pass.

### Suggested top-level modules (names are suggestions)
`ingestion` · `knowledge` (cases, citations, statutes) · `retrieval` · `privacy` · `verification` · `agents` · `rules` (deadlines, element checklists) · `drafting` (templates) · `api` · `workers` · `web` · `evaluation` · `infra` · `docs`

---

## 19. Risks, honest limits and open questions

**Known limits (show these in the product and the paper)**
- **Coverage:** the open corpus is not the full body of Indian law. Older cases and some reporters' citations may be missing. That is why "not found in corpus" is a distinct, honest result.
- **Copyright:** headnotes and editorial content from paid reporters are not available and must not be copied.
- **OCR and extraction errors** will exist, especially for old or regional-language scans. Confidence scores and lawyer review are the safeguard.
- **Outcome and "good-law" signals** are heuristic. They are labelled as signals.
- **Free LLM tiers** may change limits. The local fallback is mandatory.
- **Not legal advice.** A qualified advocate must review everything.

**Open questions for the team (decide in Phase 0/1)**
1. Which High Courts and years go into the pilot corpus?
2. Do we also want a second domain (for example, bail applications) after Section 138, or go deep on one? Recommendation: go deep on one; keep the design domain-pluggable.
3. Which local fallback LLM to use?
4. Who is the legal reviewer who will confirm the rules, templates and gold set? (Supervisor, an advocate contact, or a law-college partner.)
5. Will the paper target a legal-informatics or an NLP/AI venue? This affects which evaluations to emphasise.

---

## 20. Sources checked while preparing this document
- Indian Supreme Court Judgments, AWS Open Data Registry — https://registry.opendata.aws/indian-supreme-court-judgments/
- Indian High Court Judgments, AWS Open Data Registry — https://registry.opendata.aws/indian-high-court-judgments/
- IL-TUR: Benchmark for Indian Legal Text Understanding and Reasoning (ACL 2024) — https://aclanthology.org/2024.acl-long.618
- Domain-Partitioned Hybrid RAG for Legal Reasoning: Toward Modular and Explainable Legal AI for India — https://arxiv.org/abs/2602.23371
- Student project deck: "DocketPilot" Phase 1 (06.09.2026)

*Dataset details above came from the registry pages on 27 Oct 2026; Claude Code should re-check them in Phase 0.*
