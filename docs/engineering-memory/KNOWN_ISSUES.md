# Known issues

## SEC-001 — Security audit remediation incomplete

* Severity: P1
* Observed: initial fixes cover public demo login, privilege assignment, token expiry/revocation, direct RAG metadata, authenticated bounded file upload, process-local rate limits, admin SSE token URLs, explicit CORS, response headers, SearXNG secret fallback and share revocation.
* Remaining: MFA and renewal tokens, distributed/per-user rate limiting and hash concurrency bounds, streamed evidence-marker stripping, parser content/signature and decompression limits, shared-link expiry, complete dependency scan/upgrades, and full isolated-database suite. Production TLS/proxy/header configuration must be verified at deployment.
* Verification details: `NEXT_SESSION.md`.
* Status: partial; follow-up required.

## DB-001 — Schema evolution is runtime, not versioned

* Severity: P2
* Affected files: `backend/app/database.py`
* Reproduction: inspect `init_db()`.
* Observed: additive `ALTER TABLE` statements execute at startup; no Alembic or versioned app migration system was found.
* Expected: reviewed, ordered migrations with deployment visibility.
* Root cause: established by code inspection.
* Proposed fix: introduce a migration tool and baseline only with a safe deployment plan.
* Status: open.

## MEM-001 — Rolling summary is bounded and lossy

* Severity: P2
* Affected files: `backend/app/services/conversation_memory_service.py`, `backend/app/models/chat.py`, `backend/app/database.py`
* Observed: ordered old-message excerpts are processed once, but each excerpt caps at 500 characters and the aggregate summary caps at 4,000 characters, retaining only its tail.
* Root cause: deliberate bounded extractive summary; it is not a transcript.
* Proposed fix: evaluate usefulness before changing limits; full messages remain available through history retrieval.
* Status: partial by design.
* Regression tests: `test_16_summary_covers_messages_that_leave_recent_window_and_is_idempotent`, `test_19_concurrent_summary_updates_do_not_duplicate_excerpts`, and `test_17_summary_failure_does_not_advance_watermark`.

## QA-001 — Focused pytest result not captured

* Severity: P2
* Affected files: test execution environment.
* Observed: the runner returned partial dots and detached before pytest emitted its final summary.
* Expected: a completed report with exit status, passed/failed/skipped counts.
* Root cause: unconfirmed; likely execution-wrapper timeout/streaming behavior.
* Status: resolved for this session: focused isolated suite completed with 54 passed and 2 deselected.

## QA-002 — Full suite blocked by local runtime/storage failure

* Severity: P2
* Affected files: test environment; `backend/tests/test_security.py` triggers ingestion.
* Reproduction: `py -3.14 -m pytest -q backend/tests -m "not live" --tb=short` against isolated PostgreSQL.
* Observed: Python 3.14 access violation in Torch/Transformers during batch embedding inside ingestion. Docker then reported a read-only containerd metadata store and C: had no free bytes.
* Expected: completed suite summary and recoverable test container.
* Root cause: Python extension crash observed; Docker metadata cause is unknown.
* Proposed fix: restore Docker Desktop storage, then rerun ingestion on a supported stable Python/Torch runtime.
* Status: environment blocked; pytest counts unavailable.

## DOCKER-001 — Docker Desktop WSL data-disk startup failure

* Severity: P1 for local startup; recovered on 2026-10-27.
* Affected configuration: Docker Desktop/containerd and existing `sap_assistant_postgres` container.
* Initial evidence: read-only internal container `hosts` path, missing `runc`, containerd image blob I/O error, host port 5434 refused. A normal container start and Docker Desktop restart did not recover it.
* Root cause evidence from Docker Desktop logs: `wsl-bootstrap` failed formatting `/dev/sde` (`mkfs` exit 1), then WSL could not detach `docker_data.vhdx` (`Operation not permitted`). The deeper reason for the VHD formatting/detach failure remains unknown.
* Recovery: ran `wsl --shutdown` after saving work; then `docker desktop start`. Existing containers and volume resumed. No factory reset, volume deletion, or container removal occurred.
* Current verification: `docker compose up -d postgres searxng siftdog` succeeded; PostgreSQL is healthy on 5434; app database role connected; backend `/health` is healthy. Snapshot counts are 62 documents and 12,406 chunks. No backup artifact has been created.
* Separate health-check limitation: Compose's `pg_isready -U sap_assistant -d sap_assistant` reports server readiness but does not authenticate. The existing cluster has database `sap_assistant` but no role `sap_assistant`; app role `sap_brim_ai` works. Backend `/health` is the verified app-level connection check.
* Status: recovered; monitor Docker Desktop startup. Back up the logical cluster before any future reset/recreation.
