# Engineering decisions

## 2026-10-27 — Comparisons require grounded RAG

Context: the router's simple-definition patterns treated “difference between” SAP component questions as direct LLM answers.

Decision: route comparisons through `COMPLEX_SAP` retrieval/grounding.

Alternatives: retain direct response for speed; special-case a small set of static comparisons.

Reasoning: relationships between BRIM components are more than an acronym definition and can require product/process evidence. The change is narrow and preserves direct routing for true definitions.

Consequences: comparison questions may take longer and depend on available evidence; they gain the normal RAG safeguards. Relevant files: `services/query_router.py`, `tests/test_query_router.py`.

## 2026-10-27 — Streaming RAG uses the same supplied-chat ownership contract

Context: synchronous `/rag/query` returned 404 for an inaccessible chat ID, while the streaming endpoint did not.

Decision: reject inaccessible supplied IDs before opening the streaming flow.

Consequence: callers now receive a consistent 404 instead of an unscoped generation. Relevant file: `api/rag.py`.

## 2026-10-27 — Summarize only rows outside the recent 20, with a per-chat watermark

Context: the former updater appended only the latest exchange and could not identify older rows that had left the immediate context window.

Decision: select out-of-window rows in `(created_at, id)` order, serialize updates with a chat-row lock, and commit bounded sanitized excerpts together with a timestamp/id watermark.

Alternatives: keep appending only the current exchange; regenerate a summary from all history on every turn; introduce a separate summary table or external summarizer.

Reasoning: this fits the current Chat summary field and PostgreSQL transaction model, makes retries idempotent, and avoids extra provider calls. Full message rows and semantic retrieval remain the detailed history source.

Consequences: the 4,000-character extractive summary is lossy. It cannot guarantee preservation of every fact; messages remain separately stored. Relevant files: `conversation_memory_service.py`, `models/chat.py`, `database.py`.
