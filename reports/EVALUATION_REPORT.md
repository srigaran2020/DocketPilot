# DocketPilot — Evaluation Report (prototype)
Generated 2026-10-27T18:12:37+00:00 by `python -m docketpilot.evaluation.run_all`. Re-run to reproduce.

**Read this first.** Prototype corpus (~3 GB of open data), no lawyer review of any legal data, synthetic test data only. Numbers below are real measurements of this build; several miss the spec's targets and are reported as measured (spec 18.13).

## 1. Corpus and versions
| Item | Value |
|---|---|
| cases | 41,397 |
| with_full_text | 8,074 |
| s138_cases | 174 |
| hc_cases | 3,000 |
| chunks | 301,977 |
| citation_edges | 62,811 |
| edges_resolved | 29,012 |
| mined_aliases | 3,752 |
| sources | AWS Open Data: indian-supreme-court-judgments (metadata 1950-2026, text 2020-2026 partial), indian-high-court-judgments (sample 2023-2024); India Code (NI Act) |

| Model role | Model |
|---|---|
| llm | openai/gpt-oss-120b (Groq) |
| embedding | BAAI/bge-small-en-v1.5 |
| reranker | Xenova/ms-marco-MiniLM-L-6-v2 |

Prompt versions (sha256 prefix): `drafting_v1.md` 27b8320adfdb, `extraction_v1.md` 9eb77e9e4dd8, `verification_judge_v1.md` ef964f2b4694

## 2. Citation verification — fake-citation benchmark (spec 16.2)
Seed 13; 150 real SC cases; 756 fakes, 156 real.
| Type | n | Caught (fakes) | False alarm (real) |
|---|---|---|---|
| real | 150 |  | 0.027 |
| wrong_page | 150 | 1.0 |  |
| wrong_year | 150 | 1.0 |  |
| swapped_names | 150 | 0.98 |  |
| wrong_court | 150 | 1.0 |  |
| invented | 150 | 1.0 |  |
| proposition_real | 6 |  | 0.167 |
| wrong_proposition | 6 | 1.0 |  |

**Overall:** recall 0.996, precision 0.993, F1 0.995. Target recall >= 0.95.
Limit: fakes are derived from the same corpus the verifier searches, so this tests the verifier's logic on known cases, not coverage of all Indian law. 'Wrong proposition' rows (if present) use the Groq judge on a small sample.

## 3. Privacy — synthetic Indian PII (spec 10.1, 16.4)
| Set | Recall | Leakage | Precision |
|---|---|---|---|
| with_ner | 1.0 | 0.0 | 0.8223 |
| rules_only | 1.0 | 0.0 | 1.0 |
| heldout_with_ner | 0.9683 | 0.0317 | 0.8115 |

Target leakage < 1%. **Realistic figure: held-out leakage 3.2%** (per type: {'AADHAAR': 1.0, 'BANK_ACCOUNT': 1.0, 'ORG': 0.98, 'PERSON': 0.915, 'PHONE': 1.0}). The first two rows use templates the rules were tuned on and are optimistic. Missed items are mostly person names without cues; the lawyer preview step is the safeguard.

## 4. Retrieval (spec 16.1)
Task: SCR headnote -> same judgment's body (s.138 SC cases); n = 93 (indicative only; no lawyer-labelled gold set).
| Mode | R@1 | R@5 | MRR@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|
| lexical | 0.366 | 0.882 | 0.589 | 1234.6 | 1414.4 |
| dense | 0.699 | 0.871 | 0.772 | 446.7 | 530.9 |
| hybrid | 0.806 | 0.935 | 0.87 | 1657.8 | 1909.2 |
| hybrid_rerank | 0.806 | 0.957 | 0.861 | 8180.3 | 9397.8 |

Dense index covers Section 138 judgments only (CPU embedding speed); lexical covers all chunks.

## 5. Statute date logic (spec 16.3)
18/18 boundary checks passed across 155 NI Act sections. Checks the lookup logic against the ledger parsed from India Code footnotes. Older wordings are not stored, so 'as on' dates before the latest amendment return 'earlier_version_not_stored'.

## 6. Latency (spec 15)
| Operation | p50 ms | p95 ms / seconds | Target |
|---|---|---|---|
| exact_citation_lookup | 1.2 | 1.9 | 50 |
| statute_as_on | 2.1 | 3.1 | 50 |
| lexical_search_all_courts | 7.0 | 40.1 | 150 |
| verify_20_citation_draft_without_llm |  | 0.09 | 20 |

Step 6 (AI judge) adds roughly 2-6 s per citation with text.

## 7. End-to-end flow (Phase 6/7 acceptance)
From `reports/e2e.json` (run 2026-10-27T17:47:41.637757+00:00). Draft generation took 43.2 s.
| Step | Result |
|---|---|
| preview return_memo.txt | {"masked": 7, "leaked_values": []} |
| preview client_statement.txt | {"masked": 7, "leaked_values": []} |
| draft | {"status": "awaiting_approval", "release": "clear", "error": null} |
| approve | {"http": 200, "body": {"status": "approved", "approval": {"action": "approve", "user_id": "466e9123-85ce-47d6-98d9-9efa293ee64a", "acknowledged": []}} |
| download docx | {"http": 200, "bytes": 38791, "real_names_restored": true} |
| calendar .ics | {"http": 200, "events": 4} |

Reminders created: [{'title': 'Send the written demand notice to the drawer', 'due': '2025-08-02'}, {'title': "Drawer's time to pay after receiving the notice ends", 'due': '2025-08-02'}, {'title': 'File the complaint', 'due': '2025-09-03'}, {'title': 'Present the cheque to the bank', 'due': '2025-12-10'}]

Verification gate: {'release': 'blocked', 'approve_http': 409, 'blocked_as_expected': True}

## 8. Known limits
- Not legal advice. Nothing was reviewed by a lawyer or double-checked by the team (decision 11).
- Corpus is a small open-data sample; 'not found' is common and does not mean a case is fake.
- Most SCC/AIR citations are not resolvable (no open reporter metadata); aliases are mined heuristically.
- Only current statute wording is stored; earlier versions are reported as not stored.
- No OCR or voice input in this prototype; scanned PDFs are rejected with a message.
- Single LLM (Groq free tier); when it is unavailable, AI steps pause and say so.
