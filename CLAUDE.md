# DocketPilot

Read docs/SPEC.md first, then docs/DECISIONS.md (it records where the prototype deliberately differs from the spec).

- Git + private GitHub repo since 2026-10-28 (user's request; they are new to git: explain steps simply). After every change, commit and push (user request, 2026-10-28). Never commit `.env`, `vault/`, `data/raw/` or `data/outputs/` (see .gitignore).
- Runs locally only. Secrets (Groq key, DB password, VAULT_KEY) live in `.env`; code reads them from there.
- Start: `.\start.ps1` (databases in Docker, API from `.venv`). Checks: `.\check.ps1`. Evaluation: `python -m docketpilot.evaluation.run_all --e2e`.
- Python: `.\.venv\Scripts\python.exe`. Use 127.0.0.1, not localhost (Windows IPv6 issue). Set OPENBLAS_NUM_THREADS=1 (laptop RAM is tight).
- LLM: only `openai/gpt-oss-120b` on Groq, redacted text only; no local fallback (decision 5).
- No legal reviewer and nobody double-checks legal data (decision 11): everything legal is `unverified`; legal text must come from India Code or judgments, never from memory or the LLM; rule files quote the statute and a test checks the quote exists.
- SCR headnotes are a separate `headnote` segment, never used as evidence.
- Status 2026-10-28: general-purpose (35 Acts, any document type, decisions 27-32); open sign-up + Google sign-in. Groq free tier: one request must stay under 8,000 tokens (decision 31).
- GPU embedding: `.venv-gpu\Scripts\python -m docketpilot.retrieval.index --gpu --scope all --collection chunks_all` (after loading new texts). Never `pip install` GPU packages into `.venv`.
- Interface (since 2026-10-29): React 18 + TypeScript in `frontend/` (Vite, Tailwind, Radix UI). After changing it: `cd frontend; npm run build` (writes `docketpilot/web/dist/`, which is committed so the app runs without Node). Old one-file UI stays at `/classic`. Screens: `python tools/ui_screenshots.py OUT PAPER.txt`; usability check: `python tools/ui_usability_test.py PAPER.txt`.
- Benchmarks vs other systems: `python -m docketpilot.evaluation.benchmark_vs` -> reports/benchmark_vs.json; report in reports/COMPARISON.md.
- Never run the test suite with TEST_DATABASE_URL pointing at the main database: the test fixture rebuilds the schema.
