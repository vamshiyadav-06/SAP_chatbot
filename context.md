# SAP Knowledge Assistant (`SAP_BRIM`) — Repository Context & Technical Architecture

---

## 1. Executive Summary & Purpose

The **SAP Knowledge Assistant** (`SAP_BRIM`) is an enterprise-grade AI conversational platform and developer-managed **Retrieval-Augmented Generation (RAG)** system designed specifically for the SAP ecosystem. Its primary operational focus is **SAP BRIM** (Billing and Revenue Innovation Management), **S/4HANA**, **FI-CA** (Contract Accounts Receivable and Payable), **SAP CC** (Convergent Charging), **SAP CI** (Convergent Invoicing), and **SAP SOM** (Subscription Order Management).

The system enforces strict enterprise boundaries:
- **Strict SAP Domain Guardrails**: Non-SAP questions (recipes, sports, general coding) are systematically detected and refused before executing vector searches or expensive LLM calls.
- **Direct Database Vector Retrieval**: Chunks and embeddings are pre-computed at ingestion time. Documents are **never** re-chunked at query time; queries run directly against pre-indexed vector collections.
- **Hybrid Search & Multi-Factor Reranking**: Combines dense vector cosine similarity (via `all-MiniLM-L6-v2`) with lexical BM25/keyword matching, boosted by document headings, exact transaction code (T-code) matching, and entity validation filters.
- **Context-Aware Query Rewriting**: Multi-turn conversational memory resolves pronouns, ellipses, and follow-up queries into self-contained search questions.
- **Dual Database Architecture**: Full production support for **PostgreSQL + pgvector** (with HNSW index), with automatic zero-configuration fallback to an in-memory NumPy matrix search over local **SQLite** (`sap_assistant.db`).
- **Grounding Verification & Hallucination Guardrails**: Evaluates answer tokens against retrieved source chunks; flags answers if grounding scores fail to meet enterprise thresholds.
- **Authoritative Web Fallback**: Uses Tavily search strictly whitelisted to official SAP domains (`help.sap.com`, `community.sap.com`, `blogs.sap.com`) when internal corpus scores are insufficient.

---

## 2. High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph Client["Frontend (React 19 + Vite + Tailwind v4)"]
        UI[Chat Interface / Sidebar / Modals]
        SSE[SSE Stream Reader / Citation Cards]
    end

    subgraph API["FastAPI Backend (Uvicorn)"]
        RouterAuth[auth.py: JWT & User Management]
        RouterChats[chats.py: Sessions & History]
        RouterMsg[messages.py: Chat & SSE Streaming]
        RouterRAG[rag.py: Synchronous RAG Query]
        RouterAdmin[admin.py: Ingestion & Diagnostics]
    end

    subgraph DomainGuard["Domain Guardrails & Pre-Processing"]
        Rewriter[QueryRewriter: Multi-Turn Context Resolution]
        Classifier[SAPClassifier: Regex & Module Whitelist Guardrail]
    end

    subgraph RetrievalEngine["Dual-Stream Retrieval & Reranking"]
        Hybrid[retrieval_service.py: Hybrid Search]
        Reranker[reranking_service.py: Multi-Factor Reranker]
        TavilySearch[web_search_service.py: help.sap.com Whitelist]
    end

    subgraph DataStorage["Dual Database Layer"]
        PG[(PostgreSQL + pgvector HNSW Index)]
        SQLite[(SQLite sap_assistant.db + NumPy Matrix Fallback)]
    end

    subgraph SynthesisLayer["LLM Synthesis & Grounding"]
        LLM[llm_service.py: Groq / OpenAI / Local Extractive]
        Grounding[grounding_service.py: Term Overlap & Verification]
    end

    UI -->|HTTP / SSE| RouterMsg
    RouterMsg --> Rewriter
    Rewriter --> Classifier
    Classifier -->|Out of Scope| Rejection[Refusal Response]
    Classifier -->|In Scope| Hybrid
    Hybrid <-->|Dense & Lexical| PG
    Hybrid <-->|Dense & Lexical| SQLite
    Hybrid --> Reranker
    Reranker -->|Low Confidence / Fallback| TavilySearch
    Reranker --> LLM
    TavilySearch --> LLM
    LLM --> Grounding
    Grounding --> RouterMsg
    RouterMsg -->|SSE Stream / JSON| SSE
```

---

## 3. Repository Directory Structure

```
SAP_BRIM/
├── README.md                              # Quick-start instructions, environment setup, and architecture notes
├── docker-compose.yml                     # Docker Compose spec for PostgreSQL + pgvector
├── POST_INGESTION_VALIDATION_REPORT.md    # Empirical validation report covering 31 documents, 10,661 chunks
├── PROJECT_WORKFLOW_REPORT.md             # Detailed operational analysis and latency benchmarks
├── context.md                             # Comprehensive technical documentation (this file)
├── scratch_validation_output.json         # Raw benchmark test outputs and metrics
├── backend/
│   ├── requirements.txt                   # Backend Python dependencies
│   ├── .env.example                       # Reference environment variables template
│   ├── .env                              # Local runtime environment variables (gitignored)
│   ├── sap_assistant.db                  # Local pre-indexed SQLite vector database (gitignored)
│   ├── app/
│   │   ├── main.py                        # FastAPI application entrypoint, CORS, exception handlers
│   │   ├── config.py                      # Pydantic BaseSettings loading environment configuration
│   │   ├── database.py                    # Dual-engine connection pool (PostgreSQL with SQLite fallback)
│   │   ├── api/                           # FastAPI route handlers
│   │   │   ├── admin.py                   # Ingestion trigger and document management
│   │   │   ├── auth.py                    # User registration, login, JWT token issuance
│   │   │   ├── chats.py                   # Chat session creation, rename, delete, and list
│   │   │   ├── messages.py                # Message creation, history, and real-time SSE streaming
│   │   │   └── rag.py                     # Standalone RAG query endpoint with source attribution
│   │   ├── models/                        # SQLAlchemy ORM declarative models
│   │   │   ├── user.py                    # User account schema with password hashes
│   │   │   ├── chat.py                    # Chat conversation sessions
│   │   │   ├── message.py                 # Chat messages with role, content, and grounding metadata
│   │   │   ├── document.py                # Source document records with SHA-256 hash
│   │   │   ├── chunk.py                   # Document chunks with custom EmbeddingVector type
│   │   │   ├── citation.py                # Exact document citations mapped to messages
│   │   │   └── web_source.py              # External web sources mapped to messages
│   │   ├── schemas/                       # Pydantic schemas for request/response serialization
│   │   │   ├── auth.py, chat.py, message.py, rag.py
│   │   ├── security/
│   │   │   └── auth.py                    # Passlib bcrypt password hashing & JWT token verification
│   │   ├── services/                      # Core business logic and algorithmic pipelines
│   │   │   ├── query_rewriter.py          # Conversational context and follow-up query rewriting
│   │   │   ├── sap_classifier.py          # Strict SAP domain classifier and boundary enforcement
│   │   │   ├── embedding_service.py       # Sentence-transformers / FastEmbed ONNX embedding generator
│   │   │   ├── retrieval_service.py       # Hybrid dense + lexical retrieval (pgvector / NumPy)
│   │   │   ├── reranking_service.py       # Multi-factor score booster, entity validator, and selector
│   │   │   ├── web_search_service.py      # Tavily SAP authoritative documentation search
│   │   │   ├── llm_service.py             # Multi-model cascade (Groq -> OpenAI -> Local Extractive)
│   │   │   ├── grounding_service.py       # Grounding ratio and hallucination detection
│   │   │   ├── rag_service.py             # Master orchestrator coordinating retrieval, rerank, & LLM
│   │   │   └── document_service.py        # PDF extraction, chunking, and database insertion
│   │   └── ingestion/
│   │       └── ingest.py                  # CLI & programmatic batch ingestion engine
│   └── tests/
│       └── test_rag_and_citations.py      # Pytest test suite for end-to-end RAG verification
├── frontend/
│   ├── package.json                       # React 19, Vite, Tailwind CSS v4, Lucide dependencies
│   ├── vite.config.ts                     # Vite config with /api proxy to localhost:8000
│   ├── tsconfig.json                      # TypeScript configuration
│   ├── src/
│   │   ├── main.tsx                       # React application DOM mount
│   │   ├── App.tsx                        # Root application component with auth state & routing
│   │   ├── App.css, index.css             # Tailwind v4 import and custom UI animations
│   │   ├── pages/
│   │   │   ├── ChatPage.tsx               # Main chat workspace, streaming handler, citation popover
│   │   │   ├── LoginPage.tsx              # User login screen
│   │   │   └── RegisterPage.tsx           # User registration screen
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   │   ├── ChatInput.tsx          # Auto-resizing textarea with submit controls
│   │   │   │   ├── ChatMessage.tsx        # Markdown renderer, citation pills, grounding score
│   │   │   │   ├── CitationModal.tsx      # Modal displaying exact source chunk, page, & text
│   │   │   │   ├── GroundingScoreBadge.tsx # Visual indicator for grounding confidence
│   │   │   │   ├── SourceTypeBadge.tsx    # Badge indicating Knowledge Base vs Web fallback
│   │   │   │   ├── ShareModal.tsx         # Chat session export and share modal
│   │   │   │   └── WelcomeScreen.tsx      # Initial greeting with pre-built SAP query prompts
│   │   │   └── sidebar/
│   │   │       ├── Sidebar.tsx            # Session navigator, new chat trigger, search bar
│   │   │       └── ChatListItem.tsx       # Conversation entry with rename and delete options
│   │   ├── services/
│   │   │   └── api.ts                     # REST client for auth, chats, messages, and streaming SSE
│   │   └── types/
│   │       └── index.ts                   # TypeScript interfaces (User, Chat, Message, Citation, etc.)
├── knowledge_base/
│   ├── documents/                         # 7 core reference PDFs (CC, CI, FI-CA, pdfdownload)
│   └── the full rag data sap/             # 14 enterprise manuals (360MB, gitignored)
└── scratch/                               # Benchmark and validation scripts
    ├── run_rag_benchmark.py               # Comprehensive RAG accuracy benchmark runner
    ├── test_rewriter_logic.py             # Multi-turn query rewriter test cases
    ├── test_rewrite_prompt.py             # Prompt template validation
    ├── test_complex_brim.py               # Complex multi-step BRIM configuration tests
    ├── test_all_prompts.py                # Broad prompt validation across modules
    └── test_streaming_ux.py               # Automated verification of SSE streaming payloads
```

---

## 4. In-Depth Subsystem Analysis

### 4.1 Ingestion & Vector Storage Subsystem

#### Ingestion Pipeline (`backend/app/ingestion/ingest.py` & `document_service.py`)
1. **Document Discovery**: Recursively scans `knowledge_base/` for `.pdf` files.
2. **Idempotent File Hashing**: Calculates a SHA-256 hash for each document. If a document record with matching hash and existing chunks already exists in the database, ingestion skips the file immediately.
3. **Structure-Aware Extraction**: Uses `pypdf` to extract text page-by-page, identifying:
   - Page headers and chapter titles (stored in `section`).
   - Technical transaction codes and procedural steps.
4. **Sliding Window Chunking**:
   - Chunk length: **500 characters** with **100-character overlap**.
   - Preserves sentence boundaries and tags each chunk with `page_number`, `document_name`, `chunk_index`, and `section`.
5. **Dense Vector Generation**: Chunks are embedded in batches of 32/64 using `all-MiniLM-L6-v2` (384 dimensions).

#### Database Layer & Custom ORM Type (`backend/app/database.py`, `models/chunk.py`)
- **Dual-Engine Auto-Fallback**:
  - `get_engine()` attempts a connection to `DATABASE_URL` (PostgreSQL with pgvector) with a 1-second timeout.
  - If PostgreSQL is unreachable, it logs a warning and automatically falls back to `sqlite:///.../backend/sap_assistant.db`.
- **`EmbeddingVector` Custom TypeDecorator**:
  - On **PostgreSQL**: Maps to `pgvector.sqlalchemy.Vector(384)`. Supports HNSW index (`vector_cosine_ops`) for sub-10ms nearest-neighbor queries.
  - On **SQLite**: Serializes vector arrays into JSON text strings. At query time, `retrieval_service.py` loads vector arrays into an in-memory NumPy matrix for instant vectorized dot product multiplication.

---

### 4.2 Query Processing & Domain Guardrails

```
User Input 
    │
    ▼
[QueryRewriter] ──> Needs Context? ──YES──> Groq LLM resolves context into standalone query
    │                                  ▲
    NO (or resolved)                   │ (Previous turns: user & assistant messages)
    ▼
[SAPClassifier] ──> SAP Domain Match? ──NO──> Immediate Polite Refusal (No DB or LLM call)
    │
   YES
    ▼
[EmbeddingService] ──> Generates 384-dim Query Vector
    │
    ▼
[Hybrid Retrieval Engine]
```

#### Context-Aware Query Rewriter (`backend/app/services/query_rewriter.py`)
- **Purpose**: Solves conversational ambiguity in multi-turn dialogues (e.g., User asks *"What is Convergent Charging?"* followed by *"How is it configured in step 2?"*).
- **Heuristic Candidate Detection**:
  - Checks if query begins with ambiguous openers (*"explain in detail"*, *"why?"*, *"what are the steps"*, *"give an example"*).
  - Checks for pronouns (*"it"*, *"this"*, *"that"*, *"these"*).
  - Explicitly leaves non-SAP general queries alone so the domain classifier can properly reject them.
- **LLM Context Resolution**: Formulates a concise prompt to the fast Groq model to rewrite the prompt into a self-contained SAP technical search query before vector retrieval.

#### SAP Domain Classifier (`backend/app/services/sap_classifier.py`)
- **Boundary Enforcement**: Restricts assistant usage exclusively to the SAP domain.
- **Lexical Taxonomy**:
  - **30+ SAP Modules**: `BRIM`, `SOM`, `CC`, `CI`, `FI-CA`, `S/4HANA`, `BTP`, `FICO`, `MM`, `SD`, `PP`, `QM`, `PM`, `EWM`, `TM`, etc.
  - **Technical Concepts**: `Billable Item (BIT)`, `Consumption Item (CIT)`, `BAPI`, `IDoc`, `ABAP`, `Fiori`, `OData`, `CDS View`, `RAP`.
  - **Database Tables**: `BSEG`, `BKPF`, `MARA`, `VBAK`, `VBAP`, `EKKO`, `EKPO`, `DFKKOP`.
  - **Transaction Codes**: `FICA`, `FPCM1`, `ME21N`, `VA01`, `MIGO`, `SE80`, `SPRO`, `SM59`.
- **Regex Word Boundaries**: Prevents false positive triggers (e.g., matches `\bFI\b` or `\bCAP\b` without matching English words like `finance` or `capital`).

---

### 4.3 Hybrid Retrieval & Multi-Factor Reranking

#### Hybrid Retrieval Engine (`backend/app/services/retrieval_service.py`)
- **PostgreSQL Branch**:
  - Vector search: Calculates cosine distance `<=>` using HNSW index.
  - Lexical search: Performs full-text search using `to_tsvector('english', chunk_text)` ranked with GIN index.
  - Fusion: Combines ranks via Reciprocal Rank Fusion (RRF).
- **SQLite Fallback Branch**:
  - Vector search: `_get_cache()` maintains an in-memory NumPy matrix (`cached_matrix`) of all chunk embeddings. Runs `cached_matrix @ query_vector` for cosine similarity in ~10–18ms across 10,000+ chunks.
  - Lexical search: Multi-word term-frequency search boosting exact matches for transaction codes and technical identifiers.
  - Score Formula:
    $$\text{Hybrid Score} = 0.60 \times \text{Vector Score} + 0.40 \times \text{Keyword Score}$$

#### Multi-Factor Reranker (`backend/app/services/reranking_service.py`)
Retrieves top candidate chunks (up to 50) and computes an enriched relevance score:
1. **Section/Heading Match (+0.15)**: Boosts chunks whose document section name matches query tokens.
2. **Exact N-Gram Match (+0.12)**: Boosts chunks containing the exact multi-word user phrase.
3. **Transaction Code Match (+0.10)**: Boosts chunks containing exact T-codes found in the query.
4. **Entity Validation Filter**: Filters out false matches across distinct SAP products (e.g., cross-matching Ariba or Concur when the user explicitly queried BRIM SOM).
5. **Score Competition**: Compares the top local Knowledge Base score against live Web Search results. If the local corpus has low relevance or lacks coverage, the system automatically falls back to authoritative SAP web documentation.

---

### 4.4 Synthesis, Streaming, & Grounding Guardrails

#### LLM Synthesis Engine (`backend/app/services/llm_service.py`)
- **Multi-Model Priority Cascade**:
  1. Primary: **Groq** (`llama-3.3-70b-versatile` or `openai/gpt-oss-120b`) for sub-second token generation.
  2. Secondary: Fast Groq fallback (`llama-3.1-8b-instant`).
  3. Cloud Fallback: **OpenAI** (`gpt-4o`, `gpt-4o-mini`).
  4. Local Fallback: Deterministic extractive synthesis engine (operates completely offline by extracting verified sentences from retrieved chunks).
- **Strict Prompting**: System prompt strictly commands the LLM to base answers solely on provided context chunks and refuse extrapolation.

#### Server-Sent Events (SSE) Streaming (`backend/app/api/messages.py`)
- Endpoint: `POST /api/chats/{chat_id}/messages?stream=true`
- **Stream Events**:
  - `start`: Emits initial message ID and metadata.
  - `token`: Streams individual text chunks in real time as generated by the LLM.
  - `citations`: Emits parsed citations including document name, page number, section, and similarity score.
  - `grounding`: Emits the computed grounding verification score.
  - `done`: Finalizes the stream and persists the complete assistant response and citations to the database.

#### Grounding & Hallucination Guardrail (`backend/app/services/grounding_service.py`)
Evaluates answer grounding using four objective factors:
1. **Retrieval Quality**: Top rerank score of supporting chunks.
2. **Query Coverage**: Ratio of user query keywords present in retrieved chunks.
3. **Answer Support**: Percentage of non-stopword tokens in the generated answer that appear directly in the source evidence.
4. **Corroboration**: Evidence agreement across multiple retrieved chunks.

Threshold: Answers with a grounding score below `GROUNDING_THRESHOLD` (default: 0.65) are flagged with a warning badge in the UI.

---

## 5. Database Schema & Data Models

| Table | Primary Key | Foreign Keys | Key Attributes & Description |
| :--- | :--- | :--- | :--- |
| `users` | `id` (UUID) | None | `email`, `name`, `hashed_password`, `is_active`, `is_admin`, `created_at` |
| `chats` | `id` (UUID) | `user_id` -> `users.id` | `title`, `created_at`, `updated_at` |
| `messages` | `id` (UUID) | `chat_id` -> `chats.id` | `role` (`user` / `assistant`), `content`, `source_type` (`knowledge_base`, `web`, `refusal`), `grounding_score`, `created_at` |
| `documents` | `id` (UUID) | None | `filename`, `file_hash` (SHA-256 for idempotency), `total_pages`, `total_chunks`, `created_at` |
| `document_chunks` | `id` (UUID) | `document_id` -> `documents.id` | `document_name`, `chunk_index`, `page_number`, `section`, `chunk_text`, `metadata_json`, `embedding` (`EmbeddingVector` 384-dim) |
| `citations` | `id` (UUID) | `message_id` -> `messages.id` | `document_name`, `page_number`, `section`, `citation_text`, `similarity_score` |
| `web_sources` | `id` (UUID) | `message_id` -> `messages.id` | `title`, `url`, `domain`, `snippet` |

---

## 6. Frontend Architecture & User Experience

Built on **React 19**, **TypeScript**, **Vite**, and **Tailwind CSS v4**:

- **`ChatPage.tsx`**: Central orchestration component.
  - Manages active chat session state, message history, and optimistic UI updates.
  - Connects to the SSE streaming API via `fetch` with `ReadableStreamDefaultReader`.
  - Handles real-time token accumulation, auto-scrolling, and citation state.
- **`ChatMessage.tsx`**: Renders message bubbles.
  - Uses `react-markdown` and `remark-gfm` for syntax highlighting, formatted tables, and bullet points.
  - Renders interactive citation chips (e.g., `[Doc: SAP CC.pdf, p. 24]`).
  - Displays `GroundingScoreBadge` and `SourceTypeBadge` (`Knowledge Base` vs `SAP Web Help`).
- **`CitationModal.tsx`**: Interactive drawer/modal triggered when a user clicks a citation pill. Displays the exact document title, page number, section, similarity score, and excerpt text.
- **`Sidebar.tsx` & `ChatListItem.tsx`**: Conversation navigation drawer supporting chat search, session creation, inline renaming, and session deletion.
- **`ChatInput.tsx`**: Multi-line auto-expanding textarea supporting keyboard shortcuts (`Enter` to send, `Shift+Enter` for newline) with streaming disable states.

---

## 7. Knowledge Base Inventory & Empirical Validation

### 7.1 Indexed Dataset Overview
As recorded in `POST_INGESTION_VALIDATION_REPORT.md`:
- **Total Processed Documents**: **31 Documents**
  - 7 Core Documents (`knowledge_base/documents/`): `SAP CC.pdf`, `SAP CI1.pdf`, `SAP CI2.pdf`, `SAP CI3.pdf`, `SAP CI4.pdf`, `SAP FI-CA.pdf`, `pdfdownload.pdf`
  - 14 Enterprise Manuals (`knowledge_base/the full rag data sap/`): `BR234_EN_SOM`, `BRIM_AC240_EN_Col16`, `SAP BRIM Press Book`, `SIMPL_OP1709`, etc.
  - 10 Reference Manuals & Guides.
- **Total Pages Ingested**: **4,591 pages**
- **Total Chunks Generated**: **10,661 chunks**
- **Vector Coverage**: **100%** (10,661 vectors with 384 dimensions; zero null or dimension-mismatched vectors).

### 7.2 Empirical Benchmark Findings

| Test Category | Target / Query | Result | Verification Notes |
| :--- | :--- | :---: | :--- |
| **Transaction Code Precision** | T-code for Transfer Credit Data to SAP Credit Management in FI-CA | **PASSED** | Correctly retrieved `FPCM1` from `pdfdownload.pdf` (Page 24) with exact citation. |
| **Configuration Field Anchor** | Custom field for Billable Item Classes relevant for Credit Management | **PASSED** | Retrieved exact IMG configuration path and field structure. |
| **New Document Retrieval** | Cross-document retrieval across newly ingested manuals | **80.0%** | 4 out of 5 newly ingested documents matched in top ranks. |
| **Domain Boundary Rejection** | Non-SAP queries (e.g., general python questions, recipes, sports) | **100% Refusal** | Handled by `SAPClassifier` in < 2ms without LLM cost. |

---

## 8. Configuration & Environment Variables Reference

Key environment variables in `backend/.env`:

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | string | `postgresql://postgres:postgres@localhost:5432/sap_assistant` | PostgreSQL connection string. Falls back to SQLite if unreachable. |
| `SQLITE_FALLBACK_URL` | string | `sqlite:///.../backend/sap_assistant.db` | Local SQLite database fallback path. |
| `JWT_SECRET` | string | `sap-super-secret-jwt-key-2026-production-ready` | Cryptographic secret for signing JWT access tokens. |
| `JWT_ALGORITHM` | string | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int | `1440` (24 hours) | Expiration window for user sessions. |
| `ADMIN_API_KEY` | string | `sap-admin-dev-secret-key-999` | Secret key for triggering admin ingestion endpoints. |
| `LLM_PROVIDER` | string | `groq` | Active provider: `groq`, `openai`, or `local`. |
| `LLM_API_KEY` | string | — | API key for the selected provider. |
| `LLM_MODEL` | string | `openai/gpt-oss-120b` / `llama-3.3-70b-versatile` | Model name for generation. |
| `GROQ_API_KEY` | string | — | Dedicated Groq API key for Groq cascade and query rewriting. |
| `EMBEDDING_MODEL` | string | `all-MiniLM-L6-v2` | Sentence-transformers / FastEmbed model. |
| `EMBEDDING_DIM` | int | `384` | Dimensionality of embeddings. |
| `TOP_K` | int | `10` | Initial retrieval candidate limit. |
| `RERANK_TOP_K` | int | `4` | Top chunks supplied to LLM context window. |
| `SIMILARITY_THRESHOLD` | float | `0.60` | Minimum score threshold for retrieval. |
| `GROUNDING_THRESHOLD` | float | `0.65` | Minimum grounding score before warning flag. |
| `WEB_FALLBACK_ENABLED` | bool | `True` | Whether to trigger Tavily search when KB score is insufficient. |
| `WEB_SEARCH_API_KEY` | string | — | Tavily API search key. |

---

## 9. Developer & Operational Workflows

### 9.1 Running Locally (Without Docker)
1. **Backend**:
   ```bash
   cd SAP_BRIM
   python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   *Connects automatically to `backend/sap_assistant.db` via SQLite fallback.*
   - Swagger Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
   - Health Check: [http://localhost:8000/health](http://localhost:8000/health)

2. **Frontend**:
   ```bash
   cd SAP_BRIM/frontend
   npm install
   npm run dev
   ```
   - Application URL: [http://localhost:5173](http://localhost:5173)

### 9.2 Running with Docker (PostgreSQL + pgvector)
1. Ensure Docker Desktop is running.
2. Start the database container:
   ```bash
   cd SAP_BRIM
   docker-compose up -d
   ```
3. Run document ingestion into PostgreSQL:
   ```bash
   python -m backend.app.ingestion.ingest
   ```

### 9.3 Running Ingestion & Benchmarks
- Re-ingest knowledge base documents:
  ```bash
  python -m backend.app.ingestion.ingest
  ```
- Run the benchmark evaluation suite:
  ```bash
  python scratch/run_rag_benchmark.py
  ```
- Run automated unit and integration tests:
  ```bash
  pytest backend/tests/test_rag_and_citations.py
  ```
