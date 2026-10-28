# Implementation status

Last updated: 2026-10-27

- [x] Repository and dirty-worktree discovery recorded — git status and source inventory inspected.
- [x] Query-routing static/smoke audit — direct route decisions checked; comparison routing regression corrected; 16 parameterized route cases plus 1 stream ownership regression passed.
- [x] Focused routing, memory, and ownership regressions — 54 passed, 2 deselected against isolated PostgreSQL; exclusions were a corpus citation case and stale greeting-flow contract.
- [x] Recent ordering/window, older lexical/semantic recall, failed/missing embeddings, authenticated isolation, chat ownership, sync/stream memory parity — passed focused isolated PostgreSQL tests.
- [x] Rolling-summary coverage, idempotency, concurrent updates, rollback safety, and nullable-column migration — passed focused isolated PostgreSQL tests.
- [ ] Message embedding coverage/latency measured.
- [ ] Citation provenance and grounding correctness tested.
- [ ] Retrieval-score calibration independently evaluated.
- [ ] Repository-source and multi-source feature flags tested both enabled and disabled.
- [ ] Full backend regression suite completed — previous 331-test run terminated in Python 3.14 Torch/Transformers during admin ingestion before final counts; not rerun after Docker recovery.
- [x] Backend syntax compilation — `py -3.14 -m compileall -q backend` passed after storage recovered.
- [x] Frontend production build — `npm run build` passed after changes.
- [x] Pure follow-up regression — 1 passed, 6 deselected.
- [x] Docker Compose configuration parses with the 5434 default and resolves the normal/fresh projects to `sap_brim_pgdata` / `sap_brim_fresh_pgdata`.
- [x] Backend syntax compilation — `py -3.14 -m compileall -q backend` passed after documentation/config updates.
- [x] Frontend production build — `npm run build` passed (TypeScript and Vite).
- [x] Live Docker/PostgreSQL startup and backend health — recovered using `wsl --shutdown` then `docker desktop start`; PostgreSQL healthy on 5434, backend `/health` healthy, 62 documents and 12,406 chunks confirmed.
- [ ] Database backup created and restore rehearsal — not performed; no backup artifact exists.
