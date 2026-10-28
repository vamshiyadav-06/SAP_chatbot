# Engineering changelog

## 2026-10-28 — Initial security audit remediation

* Changed: auth/demo paths, roles/provisioning, token expiry and revocation, extraction auth/size/type checks, direct RAG output filtering, in-process rate/body limits, admin processing SSE, share revocation, CORS/security headers, SearXNG secret configuration, and related frontend flows/tests.
* Reason: address high/critical behaviors identified in the audit characterization tests. `SECURITY_AUDIT_REPORT.md` was not available in this checkout.
* Verification: focused regression suites: 20 passed; frontend tests: 10 passed; Python compilation and frontend TypeScript/Vite build passed; `git diff --check` passed. npm advisory scan failed due to unreachable registry endpoint; Python audit scanner unavailable. Full backend suite and Postgres behavior not verified.
* Remaining: see SEC-001 in `KNOWN_ISSUES.md` and `NEXT_SESSION.md`.

## 2026-10-27 — Initial audit, route correctness, and handover memory

* Changed: `backend/app/services/query_router.py`, `backend/app/api/rag.py`, `backend/tests/test_query_router.py`; added `docs/engineering-memory/` and `AGENTS.md`.
* Reason: prevent retrieval bypass for SAP component comparisons; align streaming RAG chat authorization; establish persistent handover documentation.
* Verification: backend compilation passed; frontend build passed; direct route smoke checks passed; 41 focused tests collected; 16 parameterized router cases plus 1 stream ownership regression passed. Full focused pytest final result was not captured and is not claimed as passing.
* Migration/config impact: none from this audit change. The pre-existing message-embedding/chat-summary schema change still needs live DB migration verification.
* Remaining concern: memory summary completeness and full integration verification.

## 2026-10-27 — Watermarked conversation summary and isolated regression

* Changed: `conversation_memory_service.py`, `models/chat.py`, `database.py`; expanded memory/follow-up tests and added `test_memory_schema_migration.py`.
* Reason: process messages as they leave the 20-message window in stable order, avoid duplicate updates, and commit the summary with its progress watermark.
* Verification: focused isolated-PostgreSQL run — 54 passed, 2 deselected. The full non-live run crashed in Python 3.14 Torch/Transformers during corpus ingestion. After storage recovered, backend compilation and frontend build passed, as did a pure follow-up test (1 passed, 6 deselected).
* Migration/config impact: two nullable columns (`summary_through_created_at`, `summary_through_message_id`) added using existing additive runtime migration convention. Scratch-schema test verified idempotency and preserved existing data.
* Remaining concerns: summary is lossy and capped at 4,000 characters; migration system remains non-versioned; full suite and Docker test-container cleanup are blocked by the daemon metadata error.

## 2026-10-27 — Docker/PostgreSQL port alignment and Windows startup docs

* Changed: `docker-compose.yml`, `.env.example`, `backend/.env.example`, `README.md`, and `docker.md`.
* Reason: Compose defaults/examples were inconsistent at 5435 while the stopped PostgreSQL container was configured for host port 5434; setup documentation also named the wrong volume and offered stale SQLite fallback/restore instructions.
* Configuration: aligned defaults to `127.0.0.1:5434` -> `5432`; verified the data volume name `sap_brim_pgdata`; documented that app config expects role/database `sap_brim_ai`, but the actual database catalog could not be queried.
* Verification: `docker compose config --quiet` passed; rendered config resolved port 5434 and alternate fresh-project volume `sap_brim_fresh_pgdata`. `py -3.14 -m compileall -q backend` passed. `npm run build` passed (TypeScript + Vite 8.3.3).
* Blocker at that point: Docker reported a read-only internal container `hosts` path, missing `runc`, and containerd image blob I/O error. It was subsequently recovered; see the following entry.

## 2026-10-27 — Recover Docker Desktop WSL data disk and verify application

* Recovery: Docker Desktop logs showed WSL data-disk format failure (`mkfs` exit 1) and failure to detach `docker_data.vhdx`. Ran `wsl --shutdown` then `docker desktop start`; existing containers and `sap_brim_pgdata` resumed. No container or volume was deleted.
* Verification: `docker compose up -d postgres searxng siftdog` succeeded; PostgreSQL healthy and published on 5434; read-only SQL confirmed 62 documents and 12,406 chunks plus pgvector 0.8.7. Backend `/health` returned healthy. Frontend, Swagger, Siftdog health, and SearXNG returned HTTP 200.
* Remaining: no backup created; full regression suite not rerun. Existing `pg_isready` healthcheck uses `sap_assistant`, a role absent in this cluster, and does not verify authentication. App role `sap_brim_ai` works.

## 2026-10-27 — Adaptive RAG Answer Generation, Output Budget & Root-Cause Pipeline Fixes

* Changed:
  - `backend/app/services/answer_planner.py`: Added dedicated `production_incident` archetype with mandatory 10-section structure (Executive Summary, Problem Analysis, Evidence and Findings, Root-Cause Analysis, Step-by-Step Investigation, Corrective and Recovery Actions, Duplicate Prevention and Financial Integrity, Validation and Reconciliation, Risks and Limitations, Final Recommendations) while preserving solution-design and upgrade reconciliation archetypes.
  - `backend/app/services/answer_style_router.py`: Added `production_incident` to `AnswerType` and `DOMAIN_STRUCTURED_ARCHETYPES`. Configured up to 10 sections, detailed depth, procedural steps, and 10-section layout template. Updated `render_style_instructions` to enforce adaptive length (100–250 words simple, 400–800 words intermediate, 1,200–2,000 words complex incident target).
  - `backend/app/services/evidence_selection_service.py`: Fixed chunk starvation bug in `select_strongest_evidence` where evidence was rigidly sliced to `settings.RERANK_TOP_K` (4 chunks). Implemented dynamic budget scaling (`internal_top_k` up to 16 chunks) when queries contain multiple aspects.
  - `backend/app/services/rag_service.py`: Enhanced multi-aspect query generation in `scenario_aspects` to detect complex multi-component incidents (CC, CI, FI-CA, duplicate financial records, safe recovery, reconciliation matrix) and split queries into independent aspect searches. Added structured `diagnostics` logging and metadata to `process_query` and `stream_query`.
  - `backend/app/services/llm_service.py`: Updated `EVIDENCE_AWARE_ANSWER_INSTRUCTIONS` with explicit adaptive word targets. Increased evidence context budget to `(20, 24000)` for `production_incident`. Added finish reason detection (`finish_reason == "length"`), seamless continuation logic (`_continue_gemini`, `_continue_openrouter`), and token diagnostics tracking attributes.
  - `backend/tests/test_adaptive_rag_pipeline.py`: Added 10 automated regression tests covering Tests A–F (complex production incident, simple question brevity, insufficient evidence boundaries, multi-turn context retention, finish reason continuation and diagnostic tracking, existing behavior preservation).
* Verification:
  - `py -3.14 -m pytest backend/tests/test_adaptive_rag_pipeline.py -v`: 10 passed.
  - Full regression run: `backend/tests/test_adaptive_rag_pipeline.py`, `backend/tests/test_solution_design_answers.py`, `backend/tests/test_senior_upgrade_and_reconciliation.py`, `backend/tests/test_answer_style_router.py`, `backend/tests/test_sap_restriction.py`, `backend/tests/test_citation_provenance.py`, `backend/tests/test_security.py`: 80 passed in 7.03s.
  - `git diff --check`: 0 errors.

## 2026-10-28 — Branch Creation and Knowledge Base Ingestion to Remote

* Branch created: `SE-updated-rag-kb`
* Changed: `.gitignore` updated to track all knowledge base documents under `knowledge_base/documents/`.
* Code pushed: All adaptive RAG pipeline additions, conversation memory services, streaming authorization fixes, and test suites.
* Knowledge base pushed: All 61 PDF documents (~489 MB total) pushed in sequential size-managed batches directly to `origin/SE-updated-rag-kb` without hitting HTTP request timeouts or requiring LFS bandwidth quotas.
* Verification: `git status` clean; remote branch `origin/SE-updated-rag-kb` fully synchronized.

