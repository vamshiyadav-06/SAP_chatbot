# Next session handover

Last update: 2026-10-28

## Security remediation handover (2026-10-28)

This session implemented an initial security remediation based on the untracked `backend/tests/test_security_audit_characterization.py`; the referenced `SECURITY_AUDIT_REPORT.md` was not present in the checkout. Existing user work was preserved and the characterization test was replaced with secure behavior regressions.

Changed: public demo login and browser guest/trial fallback removed; registration always creates consultant/non-admin accounts and password minimum raised to 12 characters with a bcrypt 72-byte cap; existing configured admin email is no longer auto-promoted; access JWTs shortened to 15 minutes, require standard claims and token version, and `/auth/logout` revokes all existing tokens for that user; document extraction requires authentication, reads at most 10 MiB plus one byte, and validates a file extension allowlist; synchronous and streaming direct RAG responses strip citations/evidence scores/comparison metadata for regular users; server-side process-local request limits and content-length rejection added; CORS now uses configured origins, production refuses wildcard origins and rejects HTTP; basic browser security headers added; administrator processing SSE uses Authorization header through fetch streaming instead of URL query credentials; share links have owner-controlled revocation and an explicit disclosure; hardcoded SearXNG fallback secret removed.

Verification: 20 focused backend security/auth/RAG/extraction tests passed after updating legacy tests to use authenticated test principals. Frontend `npm.cmd test` passed (10 tests), `npm.cmd run build` passed, `py -3.14 -m compileall -q backend` passed, and `git diff --check` passed. The first backend test invocation was blocked by invalid local `DEBUG=release`; setting process `DEBUG=false` allowed tests to run. `npm.cmd audit --omit=dev` could not reach the npm advisory endpoint; `pip_audit` is not installed. No dependency upgrade/lockfile resolution was completed.

Remaining security work/blockers: no MFA; no refresh-token renewal flow (short access tokens currently require re-login); rate buckets are per process and not shared across replicas, with no password-hash concurrency semaphore; content-length rejection does not protect chunked requests and multipart parsing happens before endpoint byte checks; document parser resource limits/content-signature validation need dedicated hardening; shared links have revocation but no expiry setting; validate logout/revocation against real PostgreSQL and run wider suite. Admin provisioning remains operator-managed by provisioning the account outside public registration; current startup only creates a new account when configured email is absent and does not grant privileges to an existing matching account. Production TLS termination, trusted proxy scheme forwarding, origin values, HSTS, and deployment-level CSP/security headers remain unverified assumptions. Pin/scan dependency tree using reachable scanner and review the supplied audit report if added to workspace.

Current branch: `SE-updated-rag-kb`. All adaptive RAG pipeline, conversation memory, authorization tests, and full knowledge base documents are tracked and pushed.

## Current application state

Docker Desktop was recovered after WSL logs showed `/dev/sde` formatting failed (`mkfs` exit 1) and `docker_data.vhdx` could not detach. `wsl --shutdown` followed by `docker desktop start` brought Docker Desktop back without deleting containers or volumes. The existing `sap_brim_pgdata` volume remains attached.

`docker compose up -d postgres searxng siftdog` succeeds. PostgreSQL is healthy on `127.0.0.1:5434`; `sap_brim_ai` app role/database works. Backend was launched with `py -3.14 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload`; `/health` reports healthy, 62 documents, 12,406 chunks. Frontend Vite is running at 127.0.0.1:5173. Swagger `/docs`, frontend `/`, Siftdog `/health`, and SearXNG `/` returned HTTP 200.

Database snapshot via read-only SQL: databases `postgres`, `sap_assistant`, `sap_brim_ai`, and `sap_brim_ai_test`; 62 documents, 12,406 chunks, 2 users, 1 chat, 6 messages; pgvector 0.8.7. No backup was created. Do not claim a backup exists or reset Docker/volumes before making and verifying one.

Compose health-check caveat: `pg_isready -U sap_assistant -d sap_assistant` is only a server readiness probe and does not authenticate. The `sap_assistant` database exists but the `sap_assistant` role is absent in the existing cluster; `sap_brim_ai` role connects and backend `/health` proves the app connection. Consider aligning healthcheck with an authenticated SQL query, but assess whether it will recreate the PG container and back up first.

## Checks and blockers

* `docker compose up -d postgres searxng siftdog` — passed after WSL recovery; all three containers running.
* `docker exec sap_assistant_postgres pg_isready -U sap_assistant -d sap_assistant` — readiness returned true, but see authentication caveat above.
* `Test-NetConnection 127.0.0.1 -Port 5434` — passed.
* Read-only SQL counts and vector extension — passed; see `AUDIT_REPORT.md`.
* Backend `/health`, `/docs`, frontend `/`, Siftdog `/health`, SearXNG `/` — HTTP 200/healthy.
* Backend compilation and frontend build passed in the previous task. The full backend suite previously collected 331 tests but crashed in Python 3.14 Torch/Transformers during admin ingestion before final counts; not rerun after Docker recovery.
* Full regression run on updated RAG pipeline (`backend/tests/test_adaptive_rag_pipeline.py`, `backend/tests/test_solution_design_answers.py`, `backend/tests/test_senior_upgrade_and_reconciliation.py`, `backend/tests/test_answer_style_router.py`, `backend/tests/test_sap_restriction.py`, `backend/tests/test_citation_provenance.py`, `backend/tests/test_security.py`) passed (80 passed in 7.03s).
* No DB backup/restore created yet.

## Current RAG Answer Generation State

Adaptive response generation for complex SAP BRIM scenarios has been implemented:
1. `answer_planner.py`: Added `production_incident` archetype with mandatory 10-section structure.
2. `answer_style_router.py`: `production_incident` routed with max_sections=10, detailed level, procedural steps, and 10-section layout.
3. `evidence_selection_service.py`: Dynamic scaling of internal_top_k up to 16 chunks for multi-aspect incident queries (replaces rigid 4-chunk bottleneck).
4. `rag_service.py`: Incident aspect splitting across CC, CI, FI-CA, safe recovery, and reconciliation. Diagnostic tracking in `process_query` and `stream_query`.
5. `llm_service.py`: Output continuation on length cutoff (`_continue_gemini`, `_continue_openrouter`), token diagnostic tracking, adaptive word targets (100–250 words simple, 400–800 words intermediate, 1,200–2,000 words complex incident target).
6. Tests: `backend/tests/test_adaptive_rag_pipeline.py` (10 tests covering Tests A–F) all passing.

Next three tasks:

1. Create and verify an external logical backup of `sap_brim_ai` and, if required, the full cluster before any reset/recreation.
2. Run end-to-end frontend integration tests with streaming and verifying that long Markdown answers (including all 10 incident sections) render seamlessly in the UI without markdown breakage.
3. Decide whether to repair the Compose healthcheck's nonexistent `sap_assistant` role assumption; back up first if applying the change would recreate PostgreSQL. Keep all existing volumes and unrelated containers.

Read first: `PROJECT_CONTEXT.md`, `IMPLEMENTATION_MAP.md`, `AUDIT_REPORT.md`, then `KNOWN_ISSUES.md` and the affected README/Docker configuration.

