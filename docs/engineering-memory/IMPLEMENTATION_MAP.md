# Implementation map

Last reviewed: 2026-10-27

Security audit update 2026-10-28: auth, direct RAG sanitization, extraction protection, SSE transport, sharing revocation, request limits and CORS/TLS headers changed; see `NEXT_SESSION.md` for verification and remaining blockers. The report named by the request was absent, so the untracked characterization test provided the available finding set.

| Feature | File | Function/class | Current behavior | Dependencies | Tests | Status |
| --- | --- | --- | --- | --- | --- | --- |
| App/bootstrap | `backend/app/main.py` | `lifespan`, `app` | validates security settings and initializes DB | FastAPI, database | security tests | PARTIALLY VERIFIED |
| Authentication | `backend/app/security/auth.py`, `api/auth.py` | token/user dependencies | JWT login/register/admin paths | jose, passlib | `test_auth_and_isolation.py` | UNVERIFIED THIS AUDIT |
| Chat ownership | `api/chats.py`, `api/messages.py` | ownership helpers | chat-scoped access | SQLAlchemy | auth/isolation tests | PARTIALLY VERIFIED |
| Query routing | `services/query_router.py` | `QueryRouter.route` | direct vs RAG vs memory routes | classifier, memory intent | `test_query_router.py` | PARTIALLY VERIFIED |
| Conversation window | `services/conversation_memory_service.py` | `get_recent_messages` | newest 20, chronological output | Message DB table | `test_conversation_memory.py` | VERIFIED IN FOCUSED ISOLATED TESTS |
| Long-term recall | same | `search_history` | user-scoped lexical/vector scoring; lexical fallback with missing embeddings | embeddings, Chat join | `test_conversation_memory.py` | VERIFIED IN FOCUSED ISOLATED TESTS |
| Summary | same; `models/chat.py`, `database.py` | `update_rolling_summary` | summarizes rows older than latest 20; timestamp/id watermark; row lock; sanitized excerpts; 4,000-character cap | PostgreSQL transaction | memory + schema tests | VERIFIED IN FOCUSED ISOLATED TESTS; LOSSY |
| RAG pipeline | `services/rag_service.py` | `process_query`, `stream_query` | routing, retrieval, evidence, generation, grounding | all RAG services | RAG suites | PARTIALLY VERIFIED |
| Embeddings | `services/embedding_service.py` | `EmbeddingService` | sentence-transformer vectors | torch, sentence-transformers | retrieval tests | UNVERIFIED THIS AUDIT |
| Hybrid retrieval | `services/retrieval_service.py` | `retrieve` | dense + lexical candidates | numpy, DB chunks | `test_rag_pipeline_v2.py` | UNVERIFIED THIS AUDIT |
| Reranking | `services/reranking_service.py` | `rerank_kb`, `rerank_web` | cross-encoder ranking | sentence-transformers | RAG tests | UNVERIFIED THIS AUDIT |
| Grounding/citations | `services/grounding_service.py`, `api/messages.py` | validation/persistence | validates claims and saves sources | LLM/evidence | citation/grounding tests | UNVERIFIED THIS AUDIT |
| Streaming | `api/messages.py`, `api/rag.py` | SSE generators | streams tokens and persists answer | FastAPI SSE | streaming tests | PARTIALLY VERIFIED |
| Document ingestion | `ingestion/ingest.py` | `run_ingestion` | hash-based PDF/TXT/MD indexing | extractor, embeddings | extraction tests | UNVERIFIED THIS AUDIT |
| GitHub ingestion | `retrieval/repo_store.py`, scripts | store/search/ingest | optional licensed repo chunks | feature flags | repo tests | UNVERIFIED THIS AUDIT |
| Web search | `services/search/`, `web_search_service.py` | providers/unified search | Siftdog/SearXNG/Tavily paths | network services | provider tests | UNVERIFIED THIS AUDIT |
| Frontend | `frontend/src` | `App.tsx`, pages/services | Vite SPA consuming API/SSE | React/Vite | `api.test.ts`; build | VERIFIED BUILD ONLY |

## Local deployment configuration

`docker-compose.yml` binds the `postgres` service to `127.0.0.1:5434`, uses `pgvector/pgvector:pg16`, and persists data in `sap_brim_pgdata`. `docker/postgres/init/10-create-sap-brim-ai.sh` creates the `sap_brim_ai` application role/database and vector extension only for a fresh data directory. `backend/.env.example` targets that database at port 5434. SearXNG is exposed on 8089 and Siftdog on 8088. On 2026-10-27, after WSL data-disk detach failure, `wsl --shutdown` plus `docker desktop start` recovered the engine. Runtime checks currently pass: PostgreSQL healthy, SQLAlchemy backend `/health` healthy, search containers up. Current snapshot: 62 documents, 12,406 chunks. The bootstrap role configured as `sap_assistant` is missing from this existing cluster, so `pg_isready` is not an authentication check.
