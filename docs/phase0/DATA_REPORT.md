# Phase 0 — Data Discovery Report

**Date:** 27 Oct 2026 · **Status:** draft for team review · **Scripts:** `discovery/` (all re-runnable) · **Raw samples:** `data/raw/`

Phase 0 is accepted when (1) this report exists, (2) the pilot corpus is chosen and (3) the schema is agreed. Item 1 is done. Items 2 and 3 need the team's decisions in Section 7.

---

## 1. Summary

| Source | Verdict | Key fact |
|---|---|---|
| Supreme Court (AWS open data) | **Excellent** | 43,578 reported judgments 1950–2026; 100% have an SCR citation, 99.6% a neutral citation; 99.9% of sampled pages have a text layer. |
| High Courts (AWS open data) | **Good but huge** | 1.5 TB of PDFs. Metadata has no subject/statute field, so Section 138 cases can only be found by reading the text. |
| India Code (statutes) | **Good, with a catch** | Moved to `indiacode.gov.in`; it has a public REST API with one record per section. It holds only the **current** text, so older versions must be rebuilt from amendment footnotes. |
| IL-TUR (evaluation) | **Usable for research** | CC-BY-NC-SA-4.0, gated (needs a manual access request on Hugging Face). |

---

## 2. Supreme Court dataset (`s3://indian-supreme-court-judgments`)

**Layout.** `metadata/parquet/year=YYYY/metadata.parquet` (48.6 MB total) and judgments as single PDFs at `data/pdf/year=YYYY/english/<path>_EN.pdf`, or as yearly tar files (English 22.7 GB for all years; regional-language translations are separate and larger, 74 GB in total).

**Metadata fields** (completeness over 43,578 rows):

| Field | Filled | Notes |
|---|---|---|
| title, petitioner, respondent, judge, decision_date, cnr, path | 100% | `cnr` is the eCourts case number, a good unique key. |
| citation | 100% | Always the **SCR** form, e.g. `[1990] 2 S.C.R. 987`, `[1963] SUPP. 1 S.C.R. 539`. |
| nc_display (neutral citation) | 99.6% | e.g. `2011INSC759`; needs normalising to `2011 INSC 759`. |
| disposal_nature | 97.5% | Mostly "Dismissed" (16,938), "Appeal(s) allowed" (16,193). A ready-made outcome label. |
| description | 2.8% | Only filled for 2025–26. **Not usable** to find Section 138 cases. |
| author_judge | 0% | Empty. |

**Coverage by decade:** 1950s 1,422 · 1960s 5,170 · 1970s 4,796 · 1980s 3,550 · 1990s 6,506 · 2000s 9,104 · 2010s 7,954 · 2020s 5,076. These are the *reported* (SCR) judgments, not every SC order.

**Text quality** (48 PDFs, 6 per decade, `discovery/sample_sc_pdfs.py`):
- 697 of 698 pages have a text layer, across every decade. OCR is barely needed for the SC corpus.
- Older volumes carry an embedded OCR text layer with visible errors ("Octobe~ 7", "\Vtit petition"). Newer ones have split words ("governme nt"). All pages carry the SCR margin letters A–H and running headers. **Parsing needs a cleaning step**; "has text" does not mean "clean text".
- The crude noise score (`discovery/text_noise.py`) is 2–4% of tokens in every decade. It is not sensitive enough to rank documents; a better measure is needed in Phase 2.
- Neutral citations are rarely printed inside the PDF text (1 of 48), so the metadata is the source for them.

**Headnotes: decision needed.** Every SCR PDF opens with an editorial headnote (subject line, summary, "HELD:" paragraphs with page markers like `[572-B-C]`) before the judgment itself. SCR is the Court's own official reporter, not a private publisher, but spec 5.4 says not to copy headnotes. **Proposal:** detect the headnote/body boundary, store the headnote separately and flag it, never use it as verification evidence (Step 5–6 must quote the judgment body), and do not show it as DocketPilot's own text. Team/supervisor to confirm.

**Section 138 cases in SC:** unknown until full text is read. The metadata finds only 19 (from the 2025–26 descriptions). Downloading all English SC text (22.7 GB) is needed anyway for citation resolution (spec 5.2), and gives the exact count.

---

## 3. High Court dataset (`s3://indian-high-court-judgments`)

**Size:** metadata 8.0 GB (6.0 GB for 2015–2025); PDFs 1,537 GB (1,166 GB for 2015–2025). Partitioned by `year=` / `court=` / `bench=`. PDF path: `data/pdf/year=Y/court=C/bench=B/<file name from pdf_link>`.

**Metadata fields:** court_code, title, description, judge, pdf_link, cnr, date_of_registration, decision_date, disposal_nature, court, pdf_exists.
- `title` begins with the case type: `CRL.M.C./5274/2019 of A Vs B`. This is the only way to pre-filter.
- `description` is just the **first ~290 characters of the PDF** (court header). It sometimes contains a neutral citation like `2023:DHC:2651-DB`.
- `disposal_nature` and `pdf_exists` were empty in the files checked, so outcomes must come from the text.

**Eight candidate benches, year 2023** (`discovery/hc_case_types.py`, `discovery/sample_hc_pdfs.py`; 50 random criminal-matter PDFs per bench):

| Bench | Judgments 2023 | Criminal matters | s.138 share in sample | Est. s.138 / year | Pages with text | Avg PDF |
|---|---|---|---|---|---|---|
| Telangana | 66,857 | 18,911 | 10% | ~1,900 | 80% | 124 KB |
| Punjab & Haryana | 149,388 | 76,375 | 2% | ~1,500 | 96% | 77 KB |
| Madras (Principal) | 108,552 | 37,332 | 4% | ~1,500 | 86% | 82 KB |
| Karnataka (Bengaluru) | 51,097 | 12,769 | 10% | ~1,300 | 97% | 80 KB |
| Kerala | 83,859 | 14,776 | 8% | ~1,200 | 97% | 88 KB |
| Madras (Madurai) | 72,720 | 28,813 | 2% | ~600 | 87% | 84 KB |
| Delhi (Division Bench feed) | 8,465 | 1,423 | 16% | ~230 | 100% | 180 KB |
| Bombay (Appellate side) | 41,217 | 3,669 | 4% | ~150 | 100% | 41 KB |

How to read this:
- **These are rough.** Each share rests on 1–8 matches out of 50. The real figure could be half or double. The classifier (NI Act wording, or "s.138" plus cheque wording) was hand-checked on all 28 matches: most are clearly Section 138 matters, a few mention it only once, so treat the shares as upper bounds.
- **Only 3 of 400 PDFs have no text layer at all** (all P&H). Pages below 200 characters (Telangana 20%, Madras 13%) are mostly short signature/order pages, but some will need OCR; Phase 2 must measure this properly.
- **Delhi gap:** the dataset has only the division-bench feed for Delhi (8,465 judgments). Most Delhi Section 138 work is decided by single judges, so Delhi is under-represented here.
- `pypdf` printed font warnings ("fontTools is required…") on some HC PDFs; text still came out. Install `fontTools` in Phase 2 and recheck.

**Download cost.** Section 138 cases can't be found from metadata, so we must download the criminal-matter PDFs and read them. Estimated size per year (criminal matters × average PDF size, 2023 volumes):

| Bench | GB per year | Est. s.138 cases per year |
|---|---|---|
| Kerala | 1.3 | ~1,200 |
| Karnataka | 1.0 | ~1,300 |
| Telangana | 2.3 | ~1,900 |
| Delhi (DB) | 0.3 | ~230 |
| Madras (both benches) | 5.5 | ~2,100 |
| Punjab & Haryana | 5.9 | ~1,500 |

Kerala, Karnataka and Telangana give the most Section 138 cases per GB. Madras and P&H are expensive because their criminal lists are dominated by other matters. Older years are usually smaller.

---

## 4. Statutes — India Code

- **The site has moved** from `indiacode.nic.in` to `indiacode.gov.in` (the old site shows a migration page). Spec Section 5.1 should be updated.
- The new site is a DSpace app with a public REST API (`https://indiacode.gov.in/server/api`). `robots.txt` returned a server error when checked; we will rate-limit requests (≤ 1 per second) and identify ourselves in the User-Agent.
- The NI Act, 1881 (central) has act id `AC_CEN_2_33_00042_00042_1523271998701`, with **one record per section**. The record for s.138 includes:
  - section number, heading, order number;
  - the **current** text as HTML (`section_page_note`) with numbered markers;
  - **amendment footnotes**, e.g. "Ins. by Act 66 of 1988, s.4 (w.e.f. 1-4-1989)", "Subs. by Act 55 of 2002, s.7, for certain words (w.e.f. 6-2-2003)", "Subs. by s.7, ibid., for 'within fifteen days' (w.e.f. 6-2-2003)".
- **Implication for date-aware statutes (spec 5.5):** India Code gives only the latest version. Earlier versions must be rebuilt from the footnotes (which state what words were replaced and from when) plus the amending Acts themselves. This is the amendment ledger. It can be semi-automated from footnotes, but **each rebuilt version must be checked by hand** against the amending Act before use.
- State-level copies of the same Act also exist (e.g. a Chhattisgarh entry); we use only the central record (`state_name = CENTRAL`).
- Not yet checked: BNS/IPC, BNSS/CrPC, BSA/Evidence Act, Limitation Act on the new API. Expected to follow the same pattern; confirm in Phase 2.

---

## 5. Evaluation datasets

- **IL-TUR** (`Exploration-Lab/IL-TUR` on Hugging Face): licence **CC-BY-NC-SA-4.0**, gated (request access manually). Tasks: `lner`, `rr` (rhetorical roles — useful for spec 5.3), `cjpe`, `bail`, `lsi` (statute identification), `pcr` (prior-case retrieval — useful for spec 16.1), `summ`, `lmt`. Non-commercial is fine for a student research project; keep it out of any product index (spec 5.1).
- FIRE AILA, OpenNyAI, ILDC: not checked yet; check in Phase 3 when building the retrieval gold set.

---

## 6. Proposed pilot corpus

1. **Supreme Court: all English judgments, 1950–2026** (22.7 GB, ~43,600 judgments). Needed for citation resolution and the citation graph. Section 138 cases are tagged from the text.
2. **High Courts: Kerala, Karnataka (Bengaluru) and Telangana**, criminal matters, filtered to Section 138 by text. These have the most Section 138 judgments per GB and good text layers.
   - Option A (recommended start): **2020–2025** → about 25 GB to download, roughly 20,000–25,000 Section 138 judgments kept (wide error bars).
   - Option B: **2015–2025**, as the spec suggests → roughly 45–50 GB.
   - Optionally add **Madras** if Tamil Nadu cases matter to the team or the user study (adds ~5.5 GB per year), and **Delhi DB** (cheap, 0.3 GB/year, but incomplete).
3. **Statutes:** NI Act (full, central), plus BNS/IPC, BNSS/CrPC, BSA/Evidence Act and the Limitation Act from the India Code API.

Downloads run as a resumable background job that skips files already present (as `discovery/fetch_metadata.py` does). The connection here dropped several times during Phase 0; the jobs must survive that.

---

## 7. Draft database schema (for team agreement)

PostgreSQL. Every corpus table carries **provenance**: `source`, `source_key` (bucket path or API id), `licence`, `downloaded_at`, `content_sha256`.

**Corpus**
- `courts` — id, name, court_code (e.g. `33_10`), bench_code, level (SC/HC).
- `cases` — id, court_id, cnr (unique), case_type, case_number, case_year, title, petitioner, respondent, decision_date, judges[], disposal_nature (raw), outcome (normalised: allowed/dismissed/acquitted/convicted/compounded/remanded/unknown), outcome_confidence, is_s138 (+ confidence), language, provenance.
- `case_citations` — case_id, kind (`neutral` | `scr` | `hc_neutral` | `alias`), raw, canonical (unique per kind), confidence, origin (`metadata` | `mined`). Aliases for SCC/AIR/Cr LJ mined from judgment text go here (spec 5.4).
- `documents` — case_id, object_key (MinIO), pages, text_source (`text_layer` | `ocr`), ocr_confidence, noise_score, parse_status.
- `segments` — document_id, role (`headnote` | `facts` | `issues` | `arguments` | `reasoning` | `holding` | `order` | `unknown`), page_from, page_to, char_start, char_end, text. **Headnotes are a separate role and never used as evidence.**
- `chunks` — segment_id, parent_chunk_id, char_start, char_end, page, text (vectors live in Qdrant under the chunk id).
- `citation_edges` — citing_case_id, cited_case_id (nullable when unresolved), raw_citation, sentence, signal (`followed` | `relied` | `distinguished` | `overruled` | `doubted` | `per_incuriam` | `cited`), char offset.

**Statutes**
- `acts` — id, india_code_act_id, title, act_number, year, jurisdiction (CENTRAL/state), repealed.
- `section_versions` — act_id, section_number, heading, text, valid_from, valid_to (null = in force), amended_by, source_url, footnotes_raw, provenance, `confirmed_by` / `confirmed_at` (null until a person has checked it).
- `section_mappings` — from (act, section) → to (act, section), e.g. IPC ↔ BNS, with source and confirmation.

**App (Phase 1+, sketched only):** firms, users, roles, matters, matter_documents, vault entries (encrypted, separate store), drafts and draft_versions, verification_reports and verification_items, reminders, rules (versioned data files loaded into tables), audit_log (append-only), LangGraph checkpoints.

---

## 8. Decisions needed from the team

1. ~~Pilot High Courts~~ **Decided 27 Oct 2026:** Kerala, Karnataka (Bengaluru), Telangana and Madras (both benches). No Delhi.
2. ~~Years~~ **Decided 27 Oct 2026:** 2020–2025. Estimated downloads: HC ~61 GB (Madras ~33 GB of it) + SC 22.7 GB ≈ 84 GB, against 118.6 GB free on D:. Plan: read each HC PDF as it arrives, keep Section 138 matters (PDF + text) and delete the rest, so the kept corpus is a few GB.
3. ~~SCR headnotes~~ **Decided 27 Oct 2026:** approved as proposed in Section 2 (store separately, label as editorial, never use as evidence).
4. ~~Schema~~ **Agreed 27 Oct 2026** as in Section 7, with no changes requested. It will be refined as tables are built.
5. **IL-TUR:** someone on the team must request access on Hugging Face and accept the licence (needed by Phase 3).
6. ~~Legal reviewer~~ **Decided 27 Oct 2026: there will be no legal reviewer.** See Section 10.

## 10. Working without a legal reviewer

The spec assumed a lawyer would confirm the legal rules, statute versions, templates and gold set (spec 3, 9, 16, 18.4). There won't be one, so:

- **Every legal item is traced to a primary source** (India Code text, the amending Act or Gazette notification, or the judgment) with the exact passage stored next to it. Nothing comes from memory or from an LLM.
- **Two team members check each item independently** (statute versions, deadline rules, element checklist, gold labels) and record who checked it and when. Disagreements are resolved against the source text and logged. For gold labels, inter-annotator agreement is reported in the paper.
- **Status labels:** items move from `unverified` to `team-verified (source-checked)`. Nothing is ever marked `lawyer-confirmed`. The product shows "Not reviewed by a lawyer" on rules, deadlines and templates.
- **Evaluation relies more on public benchmarks** (IL-TUR, and others if their licences allow) and on checks that need no legal judgement: does a citation exist, does a quote match, is the statute text identical.
- **The paper states this as a limitation:** legal rules and templates were checked against primary sources by the student team, not by a practising advocate.

## 9. Changes to the spec suggested by these findings

- 5.1: India Code URL is now `indiacode.gov.in`, accessed through its REST API.
- 5.1/5.4: SC metadata gives SCR + neutral citations; SCC/AIR/Cr LJ must be mined (as the spec expected).
- 5.3: SCR headnote handling (Section 2 above).
- 5.5: India Code holds current text only; versions are rebuilt from footnotes plus amending Acts, with a hand check.
- 5.2: Delhi single-bench judgments are not in the open dataset.
