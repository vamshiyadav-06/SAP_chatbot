# Staging deployment readiness audit

**Updated:** 2026-11-05  
**Scope:** repository-side staging controls, authentication/registration, AI request reliability, and repeatable verification. No live Ubuntu server, Git remote, existing database volume, or real AI provider was used.

## Readiness summary

The repository changes close the application-side staging gate and registration defaults, and add isolated staging/E2E deployment procedures. A real staging rollout is **not yet verified**: Docker Engine is unavailable in this environment, so neither image build nor a fresh Compose database could be created here. Keep staging private until the Docker, browser, load, and recovery checks below have completed on an isolated Ubuntu staging VM.

## Findings and disposition

| Priority | Finding | Change | Evidence / status |
|---|---|---|---|
| P0 | New deployments could expose the app or registration by default. | Registration defaults off in backend and frontend build; staging Caddy applies Basic auth to every route except `/health`; staging binds to `127.0.0.1`; preflight requires the gate, closed registration, and loopback bind. | `test_deployment_config.py` and frontend registration tests passed in focused runs; see test log below. No public bind or live server was exercised. |
| P0 | Staging could share production database state or use copied production secrets. | Staging uses `sap_brim_staging` Compose project/volumes and fresh generated secrets; deployment refuses an incomplete staging config. The E2E stack has its own project/volume and local fake provider. | Compose/preflight regression tests passed. Docker was unavailable, so a physical staging database and image were not created. |
| P0 | Deployment recovery was not repeatable or demonstrable. | Added a fresh-volume Ubuntu procedure and a recovery script that restores a retained custom-format dump into a timestamped separate database, without a database-drop or volume-delete path. | Static review and script compilation only. Runtime recovery remains unverified pending Docker on the isolated staging VM. |
| P1 | Refresh tokens were not securely rotated on use. | Refresh uses an HttpOnly cookie, one-use rotation, server-side token hashes, and reuse detection. | `test_refresh_tokens.py`: **30 passed**; frontend API/auth tests passed; browser flow remains unverified. |
| P1 | A temporary startup network/5xx error could log out a valid user. | Concurrent refreshes are deduplicated; transient refresh/startup failures retain the cached profile and token state. | Frontend API/auth tests passed; browser flow remains unverified. |
| P1 | Provider fallback could append a second answer after a partial stream or issue a second generation after a stream failure. | Streaming errors after output are terminal; finish reasons are checked; continuation stays on the same model; failure before output returns unavailable without a non-stream retry. | `test_ai_reliability.py` passed in a focused run (see evidence). Fake clients only; no provider keys were set. |
| P1 | Stop/cancellation could leave an SDK stream consuming tokens. | Groq, Gemini, and OpenRouter streams are closed when the client cancels. | Stop/cut-off regressions passed with fake stream clients. Provider-network cancellation is not exercised. |
| P1 | AI calls/retries could exceed a request's time budget. | Request-wide deadlines cap SDK timeouts; deadline failures do not penalize model cooldowns. | Deadline and partial-output regression tests passed in the focused suite. Provider-network timing is not exercised. |
| P1 | Provider errors could log moderation or user prompt text. | Error logs record exception class, status, and category, not provider response bodies. | Log privacy regressions passed in the focused AI reliability suite. |
| P2 | User messages, prompt context, recalled history, or attachments could exceed configured request budgets. | Added message-length validation, bounded prompt/history/attachment packing, and a final external-prompt size cap. | Prompt/message/attachment budget regressions passed in the focused AI reliability suite. |
| P2 | Empty environment values did not reliably disable Tavily in local verification. | `WEB_SEARCH_API_KEY=disabled` now prevents Tavily client creation, so an explicit sentinel fails closed. | Provider/search fallback module passed with the disabled sentinel; the regression also asserts no result and no client call. |

## Verification evidence

Commands were run from the repository. Backend verification used the repository `.venv`, `DEBUG=False`, `HF_HUB_OFFLINE=1`, and a `*_test` database. The runner initially attempted to blank provider/search keys, but Pydantic Settings ignored empty variables and read configured values from the local `.env`. I discovered this after the full run reached a provider-availability test. Aggregate logs do not establish whether any earlier backend test made a billable provider request; that is unverified. Do not treat that broad run as provider-isolated. Later provider tests used an explicit disabled allowlist, nonempty sentinel keys, and web fallback off; they used fake SDK clients and the Tavily disabled sentinel.

| Check | Result |
|---|---|
| `pytest backend/tests/test_ai_reliability.py backend/tests/test_deployment_config.py -q` | **71 passed** (21.26 s); AI calls are mocked by this suite. |
| `pytest backend/tests/test_refresh_tokens.py -q` | **30 passed** (27.48 s). |
| Preflight/account + solution-design follow-up after correcting test isolation/imports | **28 passed** (15.27 s). |
| `pytest backend/tests/test_conversation_memory.py -vv -x` | **19 passed** (15.47 s), including the now charge-free empty-history path and concurrent summary update. |
| `npm.cmd test` | **39 files, 249 tests passed** (7.34 s). |
| `npm.cmd run build` | **Passed**; TypeScript and Vite production build completed. |
| `npm.cmd run test:e2e -- --list` | **Passed discovery**; 3 Playwright tests listed. Browser tests were not executed. |
| Python `py_compile` on changed AI/API/schema/RAG modules, focused tests, preflight, and `scripts/staging/test-load.py` | **Passed** in the final static check. |
| `docker compose ... build`, actual browser tests, staging load run, staging DB restore/recovery | **Not run**; Docker Engine is unavailable here. |
| First full `pytest backend/tests -q -x --basetemp .pytest_tmp_20261105_audit` | **500 passed, 2 skipped, then 1 failure** at 51%: `test_web_search_returns_no_results_when_tavily_is_unavailable` got a `MagicMock` because the configured Tavily client was available. Provider isolation was not established, so this is not a clean full-suite result. |
| Safe non-live `pytest backend/tests -m "not live" -q -x --basetemp .pytest_tmp_20261105_safe` | **112 passed, 7 deselected, then a fixture setup error**: local PostgreSQL at `127.0.0.1:5434` closed during test startup. No full-suite total; database restart/recovery was not attempted. Provider allowlist and web fallback were disabled, and settings were verified with nonempty sentinel values. |
| Broader account/reliability selection (`test_preflight_and_accounts`, `test_audit_access`, `test_query_router`, `test_repo_retrieval_and_comparison`, `test_solution_design_answers`, `test_source_registry_and_web_sources`, `test_tavily_image_retrieval`) | **110 passed** (53.85 s) after correcting two preflight fixtures to set required Basic-auth env and importing the LLM module explicitly in one test. |
| `test_audit_auth.py::test_f06_memory_backend_caps_keys_and_expires_buckets` | **1 passed**; corrected the test to advance from the real monotonic timestamp rather than moving time backwards. |
| Provider-isolation attempt with empty environment values | **Invalidated**: empty values do not override `.env` in this Settings configuration. Future backend runs need a nonempty disabled-provider sentinel, `LLM_ALLOWED_PROVIDERS=disabled`, and `WEB_FALLBACK_ENABLED=False`. |
| `pytest backend/tests/test_provider_search_fallbacks.py -q` under the disabled-provider configuration | **9 passed** (83.78 s). |

## Ubuntu staging procedure

See [STAGING_DEPLOYMENT.md](../STAGING_DEPLOYMENT.md). It starts a separate Compose project with a fresh database volume, local-only web binding, closed registration, and Basic auth. The fake-provider E2E overlay uses a separate project/volume and never routes requests to Groq, Gemini, or OpenRouter. The bounded load script sends authenticated reads only; the recovery script retains both dump and restored database for review.

Before calling staging ready, run the Ubuntu procedure and attach actual evidence for:

1. `scripts/staging/deploy.sh` image build, preflight, and healthy startup.
2. Playwright app/gate/registration checks (plus streaming only against the local fake provider).
3. `scripts/staging/test-load.py` against a short-lived tester token and the read-only chat list endpoint.
4. `scripts/staging/test-recovery.sh` with the restored Alembic revision recorded.

Keep ports 80/443 closed or loopback-bound until the access gate and registration checks pass. Do not run against the live Ubuntu host without separate approval. Do not delete volumes or recovery artifacts as cleanup.
