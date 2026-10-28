# Clyptus.AI — SAP BRIM Enterprise Knowledge Assistant

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/Frontend-React%2019-61DAFB.svg?style=flat&logo=react)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/Language-TypeScript-3178C6.svg?style=flat&logo=typescript)](https://www.typescriptlang.org/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)

**Clyptus.AI** is an enterprise-grade AI Solution Architect and Retrieval-Augmented Generation (RAG) assistant purpose-built for **SAP Billing and Revenue Innovation Management (BRIM)**, SAP S/4HANA, and enterprise billing systems.

It combines hybrid dense vector search, BM25 lexical retrieval, cross-encoder reranking, multi-tier LLM streaming, strict claim grounding, and a secure **Role-Based Admin Control Center**.

---

## 🚀 Local Development Setup

The verified setup below is for Windows PowerShell. Database initialization and Docker storage recovery are not routine startup steps.

### A. Prerequisites

- **Python:** 3.10+ is the minimum stated by the existing README. The repository has no `pyproject.toml` or `.python-version` pin. Python 3.14 compilation succeeded in the last audit, but a full test run crashed in the installed Torch/Transformers stack; runtime compatibility is therefore not established for every Python release.
- **Node.js and npm:** Vite in the lockfile requires Node.js `^20.19.0` or `>=22.12.0`. Install Node.js with npm; use `npm ci` to honor `frontend/package-lock.json`.
- **Docker Desktop:** required for PostgreSQL 16 + pgvector, SearXNG, and Siftdog. If Docker Desktop uses its WSL2 engine, keep the data volume in Docker-managed storage and do not edit Docker's internal WSL files.
- **Git** and Windows PowerShell.

### B. Project Structure

- `backend/app/` contains the FastAPI app, database setup, SQLAlchemy models, API routes, retrieval, and RAG services.
- `backend/requirements.txt` lists Python dependencies; `backend/.env.example` is the backend settings template.
- `frontend/` contains the React + TypeScript client. Vite serves it on port 5173 and proxies `/api` to port 8000.
- `docker-compose.yml` defines `postgres`, `searxng`, and `siftdog`. `docker/postgres/init/` creates the initial `sap_brim_ai` role/database and pgvector extension only when PostgreSQL initializes an empty data directory.
- `knowledge_base/documents/` is the source document tree used by ingestion. PostgreSQL stores indexed documents, chunks, embeddings, and application data.

### C. Environment Setup (Windows PowerShell)

Run from the repository root. These guarded copy commands preserve any existing local environment files:

```powershell
Set-Location -LiteralPath 'C:\Users\yuvar\OneDrive\Desktop\gen ai and agentic ai\super admin portal\sap_2.o\SAP_BRIM_Ai'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
notepad .env
notepad backend/.env
```

For a genuinely new installation, set strong local values for `POSTGRES_PASSWORD` and `SAP_BRIM_DB_PASSWORD` in root `.env`. For an existing installation, preserve the current values; changing a local environment value does not change the password already stored for a PostgreSQL role. Ensure root `POSTGRES_HOST_PORT=5434` and `backend/.env` `DATABASE_URL` targets role/database `sap_brim_ai` on `127.0.0.1:5434`, with a password matching that existing role. Also set a private `JWT_SECRET` (at least 32 characters) and provider keys needed for the features you use. Keep both `.env` files local; never paste their contents into logs or commit them. URL-encode any reserved characters in the database password inside `DATABASE_URL`.

Create the backend environment and install dependencies once:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
```

### D. Start the Application from a Fresh Terminal

**Terminal 1 — Docker and database.** Start Docker Desktop, wait until its engine is ready, then from the repository root:

```powershell
docker info --format 'Docker Engine {{.ServerVersion}}'
docker compose up -d postgres searxng siftdog
docker compose ps
docker inspect --format '{{.State.Status}} / {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' sap_assistant_postgres
docker exec sap_assistant_postgres pg_isready -U sap_assistant -d sap_assistant
Test-NetConnection 127.0.0.1 -Port 5434
docker exec sap_assistant_postgres psql -X -U sap_brim_ai -d sap_brim_ai -c "SELECT current_database(), (SELECT count(*) FROM documents) AS documents, (SELECT count(*) FROM document_chunks) AS chunks; SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

The database must report healthy/accepting connections, the port test must succeed, and the SQL query must return database `sap_brim_ai` and the existing row counts. Do not proceed as if an empty database were recovered data. Search services are optional for basic chat but are used when web fallback is enabled; their host ports are 8089 and 8088.

**Terminal 2 — FastAPI.** From the repository root:

```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 3 — React/Vite.** From the repository root:

```powershell
Set-Location frontend
if (-not (Test-Path node_modules)) { npm ci }
npm run dev
```

### E. Start After a Windows Restart

Open Docker Desktop and wait for it to finish starting. Then use three PowerShell terminals:

**Terminal 1 (repository root):**

```powershell
Set-Location -LiteralPath 'C:\Users\yuvar\OneDrive\Desktop\gen ai and agentic ai\super admin portal\sap_2.o\SAP_BRIM_Ai'
docker info --format 'Docker Engine {{.ServerVersion}}'
docker compose up -d postgres searxng siftdog
docker compose ps
```

**Terminal 2 (repository root):**

```powershell
Set-Location -LiteralPath 'C:\Users\yuvar\OneDrive\Desktop\gen ai and agentic ai\super admin portal\sap_2.o\SAP_BRIM_Ai'
.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 3 (repository root):**

```powershell
Set-Location -LiteralPath 'C:\Users\yuvar\OneDrive\Desktop\gen ai and agentic ai\super admin portal\sap_2.o\SAP_BRIM_Ai\frontend'
npm run dev
```

Dependencies and environment files are setup-time tasks; do not reinstall them or reinitialize PostgreSQL on every start.

### F. Health Checks and Troubleshooting

```powershell
docker info --format 'Docker Engine {{.ServerVersion}}'
docker compose ps
docker logs --tail 80 sap_assistant_postgres
docker exec sap_assistant_postgres pg_isready -U sap_assistant -d sap_assistant
Test-NetConnection 127.0.0.1 -Port 5434
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173
```

- **Stopped container:** if `docker info` works and the container is simply exited, inspect its logs, then use `docker compose up -d postgres`. This task's current container cannot start because Docker reports a read-only internal `hosts` path; do not recreate it until Docker storage is healthy.
- **Unhealthy PostgreSQL:** inspect `docker inspect` health output and `docker logs`; wait for recovery and confirm `pg_isready` before starting the backend.
- **Connection refused:** check container state, `docker compose ps`, and `Test-NetConnection`. Compose binds PostgreSQL to `127.0.0.1:5434` → container port 5432. `backend/.env` must use the same host port.
- **Missing host-port mapping:** inspect with `docker inspect --format '{{json .HostConfig.PortBindings}}' sap_assistant_postgres`. Reconcile the container only after Docker storage is healthy; do not remove the data volume.
- **Database authentication/name error:** expected application database/role are both `sap_brim_ai`; bootstrap account/database are `sap_assistant`. Confirm root `SAP_BRIM_DB_PASSWORD` matches the password encoded in backend `DATABASE_URL`. The init script runs only for an empty volume; editing it does not change an existing database.
- **Docker `read-only file system`, containerd I/O, or missing `runc`:** this is a Docker Desktop/WSL2 engine storage/runtime failure, not a PostgreSQL password or database-name error. Check `docker desktop logs --priority 2 --since '15 minutes ago'`. If Docker Desktop reports `docker_data.vhdx` could not detach and recommends shutdown, save work in all WSL distributions, run `wsl --shutdown`, then `docker desktop start`. This stops WSL distributions but does not delete Docker data. Recheck `docker desktop status`, container state, PostgreSQL readiness, and port 5434. Do not factory reset Docker Desktop or edit internal storage.
- **Frontend cannot reach API:** confirm backend is listening on 127.0.0.1:8000; Vite proxies `/api` to `http://localhost:8000`.

### G. Database Backup and Recovery

Only run backups when Docker and PostgreSQL are healthy. Store backups outside the repository because they contain application data. A database dump is a logical backup; it does not copy the Docker engine or volume metadata.

Create a custom-format backup of the application database:

```powershell
$backupDir = Join-Path $HOME 'Documents\SAP_BRIM_AI_Backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupFile = Join-Path $backupDir ("sap_brim_ai-{0}.dump" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
docker exec sap_assistant_postgres pg_dump -U sap_assistant -d sap_brim_ai -Fc -f /tmp/sap_brim_ai.dump
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed; no backup was verified.' }
docker cp sap_assistant_postgres:/tmp/sap_brim_ai.dump $backupFile
$dump = Get-Item $backupFile
if ($dump.Length -le 0) { throw 'Backup file is empty; do not proceed.' }
$dump | Select-Object FullName, Length, LastWriteTime
```

For a full logical export of every database and role in the cluster, also create a `pg_dumpall` backup and keep it outside the repo. This includes role password hashes, so treat it as sensitive:

```powershell
$clusterFile = Join-Path $backupDir ("sap_brim_cluster-{0}.sql" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
docker exec sap_assistant_postgres pg_dumpall -U sap_assistant -f /tmp/sap_brim_cluster.sql
if ($LASTEXITCODE -ne 0) { throw 'pg_dumpall failed; no cluster backup was verified.' }
docker cp sap_assistant_postgres:/tmp/sap_brim_cluster.sql $clusterFile
$dump = Get-Item $clusterFile
if ($dump.Length -le 0) { throw 'Cluster backup file is empty; do not proceed.' }
$dump | Select-Object FullName, Length, LastWriteTime
```

Verify that each dump file exists and has nonzero length before any reset or recreation. Keep a second copy on separate storage. Logical dumps preserve database contents and roles, not Docker engine metadata. The current Docker storage error prevents creating or verifying a backup in this environment; no backup is claimed.

To restore the custom-format dump without overwriting the existing database, copy it into the container and restore to a new, empty database name. First verify that the target name is unused:

```powershell
$backupFile = 'C:\path\to\verified\sap_brim_ai.dump'
docker exec sap_assistant_postgres psql -X -U sap_assistant -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = 'sap_brim_ai_restore';"
```

Only if that query returns no row, create the separate target and restore:

```powershell
docker cp $backupFile sap_assistant_postgres:/tmp/sap_brim_ai.dump
docker exec sap_assistant_postgres createdb -U sap_assistant -O sap_brim_ai sap_brim_ai_restore
docker exec sap_assistant_postgres pg_restore -U sap_assistant -d sap_brim_ai_restore --no-owner --role=sap_brim_ai /tmp/sap_brim_ai.dump
```

Verify counts and the vector extension before changing `DATABASE_URL` to use that restored database. Never restore over an existing target as part of troubleshooting. Before resetting Docker Desktop itself, use Docker Desktop's supported backup/recovery method for its managed data in addition to logical database backups; do not manipulate its internal WSL files.

### H. Rebuilding from Scratch (Not Normal Startup)

A fresh database starts empty and will not contain the current SAP BRIM knowledge base until ingestion is run. The init SQL creates the database and vector extension only on a newly initialized volume; backend startup creates application tables and applies the current additive schema setup.

To recreate only the PostgreSQL container while retaining the current data, first verify a backup and confirm Docker storage is healthy:

```powershell
docker volume inspect sap_brim_pgdata
docker compose up -d --force-recreate postgres
docker volume inspect sap_brim_pgdata
```

This reuses the Compose volume and does not remove it. Do not run it while the current read-only/containerd errors persist.

For a **separate fresh volume while preserving `sap_brim_pgdata`**, first verify Docker storage is healthy and take/verify backups. The fixed container name allows only one project container at a time:

```powershell
docker compose rm -sf postgres
docker compose -p sap_brim_fresh up -d postgres
docker volume ls --filter name=sap_brim_fresh_pgdata
```

This removes the old Compose container but does not use `-v`; the existing named volume is retained. The new project uses a distinct volume and has a name collision with the normal container while both are present. Return to the existing database with:

```powershell
docker compose -p sap_brim_fresh rm -sf postgres
docker compose up -d postgres
```

Verify the volume names before switching.

Deleting a database volume is a separate, permanent data-loss operation. Never use `docker compose down -v` or volume removal as routine startup or recovery. Do not delete `sap_brim_pgdata` without an independently verified backup and explicit review of every database stored there.

### I. API and Frontend URLs

- Frontend: `http://127.0.0.1:5173`
- FastAPI: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`
- Swagger/OpenAPI UI: `http://127.0.0.1:8000/docs`
- SearXNG: `http://127.0.0.1:8089`
- Siftdog: `http://127.0.0.1:8088` (health route `/health`)
- PostgreSQL: `127.0.0.1:5434` (not an HTTP URL)

### J. Known Limitations

- Docker Desktop storage/startup failure was recovered on 2026-10-27 after logs showed data-disk formatting failure and failure to detach `docker_data.vhdx`. `wsl --shutdown` followed by `docker desktop start` restored the engine; the existing `sap_brim_pgdata` volume was retained. PostgreSQL and FastAPI are currently healthy. Read-only counts showed 62 documents and 12,406 chunks; no backup has been created yet.
- This repository has no versioned migration framework; `init_db()` performs table/index creation and additive runtime schema changes.
- PostgreSQL init scripts are not rerun for an existing data volume.
- The full backend regression suite previously crashed in Python 3.14 Torch/Transformers during ingestion; see the engineering audit for exact results.

---

## 🔐 Credentials & Role-Based Access

On first start, the backend creates a Super Admin from `SUPER_ADMIN_EMAIL` and `SUPER_ADMIN_PASSWORD` in `backend/.env` (password: at least 12 characters). An existing account's password is never overwritten; to change it, run:

```bash
python backend/scripts/set_admin_password.py admin@example.com
```

The backend refuses to start if `JWT_SECRET` (required) or `ADMIN_API_KEY` (optional) is shorter than 32 characters or is a value that was ever published in this repository.

| Portal | URL | Email | Password | Access Privileges |
| :--- | :--- | :--- | :--- | :--- |
| **Admin Control Center** | [http://localhost:5173/admin/login](http://localhost:5173/admin/login) | `SUPER_ADMIN_EMAIL` | `SUPER_ADMIN_PASSWORD` | Full Document Management, Ingestion Pipeline, Internal Sources Repository, Chunk Sandbox, System Security |
| **Standard User Chat** | [http://localhost:5173/app](http://localhost:5173/app) | *Any registered user* | *User password* | Enterprise Chat, Document Attachment Analysis, Recommended Follow-ups *(Sources and internal retrieval details strictly hidden)* |

> [!NOTE]
> Regular users can register freely at `/login?mode=register` or use the guest preview. Regular users **never see internal citations, document paths, or retrieval mechanics** — they receive clean, authoritative guidance.

---

## ⚡ Core Features & Capabilities

### 1. Real-Time Progressive Streaming (ChatGPT-Style)
* **Live Token-by-Token SSE Stream**: Answers stream progressively line-by-line as generated.
* **Animated Typing Indicator**: Displays a clean `"Thinking..."` state with animated dots while preparing retrieval.
* **Blinking Terminal Cursor**: Follows active generation in real time with auto-scrolling.
* **Follow-up Recommendations**: Generates exactly 3 clickable follow-up questions tailored to the response.

### 2. Enterprise Document Attachment & Extraction
* Upload PDF, DOCX, or text files directly in the chat input.
* Automatic text extraction, page parsing, and dedicated RAG grounding against uploaded files.

### 3. Role-Based Admin Control Center (`/admin`)
* **Document Manager**: Upload, view, re-index, or remove enterprise documentation with real-time status badges (Indexed, Processing, Vectorized).
* **Internal Sources Repository**: Search and inspect indexed technical source files and page counts.
* **Retrieval & Chunk Sandbox**: Test queries against the vector database, view top-k semantic matches, inspect similarity scores, and review reranking breakdowns.
* **Security & IP Protection**: Enforces backend token authentication (403 Forbidden on admin APIs for non-admins) and strips internal citations from regular user responses.

### 4. Multi-Tier Grounded RAG Pipeline
* **Tier 1 (Dense Search)**: 384-dimensional dense vectors generated by `sentence-transformers/all-MiniLM-L6-v2`.
* **Tier 2 (Lexical Search)**: BM25 keyword matching for exact SAP transaction codes, tables (`DFKKKO`, `FKKVKP`), and BAPIs.
* **Tier 3 (Cross-Encoder Reranking)**: `cross-encoder/ms-marco-MiniLM-L-6-v2` calibrates final relevance scores.
* **Tier 4 (Tavily SAP Web Fallback)**: Automatically queries authoritative `help.sap.com` documentation when internal confidence is weak.

### 5. Adaptive Answer Formatting
* Each answer is laid out to fit the question: a direct answer, a technical explanation, a comparison, step-by-step instructions, troubleshooting, or document research.
* Tables appear only for comparisons, genuinely tabular data, or when the user asks for one. Explicit requests such as "in a table", "without a table", "briefly" or "step by step" are followed.
* Grounding, claim verification and citations work exactly as before; only the layout changes.

---

## 📝 Recent Changes (2026-10-21)

### Chat experience
| Change | What it does | Main files |
|---|---|---|
| Removed "Relevant images" | Answers no longer show a web-image gallery, and the backend no longer calls Tavily for images. The `images` field stays in responses (always empty) so nothing that reads it breaks. | `ChatMessage.tsx`, `rag_service.py` |
| Chat-app layout | Your questions appear on the right in a bubble; answers stay on the left. | `ChatMessage.tsx` |
| Copy / Share / Edit under each question | **Copy** copies the question. **Edit** rewrites it: the old answer and every later message are deleted and a new answer is streamed. Files attached to the original question stay attached. | `ChatMessage.tsx`, `ChatPage.tsx`, `messages.py` |
| Share prompt dialog | **Share** opens a dialog with a preview and Copy link / X / LinkedIn / Reddit. The link (`/share/<token>`) opens a public page showing only the question text (never the answer, files or file names) with an "Ask Clyptus.AI this question" button that pre-fills the chat input. | `SharePromptModal.tsx`, `SharedPromptPage.tsx`, `shared.py`, `shared_prompt.py` |

### Answer Style Router
Answers used to come back as large Markdown tables with repeated sections. The cause was the prompts: the system prompt asked for "structured tables", and every question type was forced into a fixed 4–7 section template.

* **`answer_style_router.py`** (new) builds an internal answer plan once per question: `answer_type`, `detail_level`, `needs_table`, `needs_steps`, `needs_citations`, `source_mode` (internal / web / hybrid) and `max_sections`.
* **Rules first**, building on the existing `answer_planner` categories. Only questions the rules cannot place get one small, cached LLM classification, validated with Pydantic. Any failure falls back to a balanced technical explanation.
* **Prompts**: the rigid section templates are replaced by a short format directive plus formatting rules (answer first, no tables by default, state each fact once, no recap sections, cite only real `[E#]` IDs). The upgrade/reconciliation and block/restriction templates are kept because they carry safety content.
* **Pipeline**: the plan is routed once and reused for streaming, the fallback answer and repair. It is recorded only in the admin-only `validation_audit` and never streamed to users. SSE events are unchanged.
* **Fix**: `answer_planner` matched error words as substrings, so "issued" or "prefix" were treated as troubleshooting. It now matches whole words.

Live example ("How does SAP Convergent Invoicing aggregate billable items?"): before, 3,063 characters with a 7-row table holding paragraphs; after, about 1,100 characters with a direct answer and three cited bullets.

New settings (all optional; defaults shown):

| Setting | Default | Purpose |
|---|---|---|
| `ANSWER_STYLE_ROUTER_ENABLED` | `True` | `False` restores the previous template prompts |
| `ANSWER_STYLE_LLM_CLASSIFIER_ENABLED` | `True` | LLM classification for questions the rules cannot place |
| `ANSWER_STYLE_CLASSIFIER_MODEL` | `openai/gpt-oss-20b` | Groq model used for that classification |
| `ANSWER_STYLE_CLASSIFIER_TIMEOUT` | `4.0` | Seconds before falling back |
| `ANSWER_STYLE_DEFAULT` | `technical_explanation` | Style used when classification fails |
| `ANSWER_STYLE_DEFAULT_DETAIL` | `balanced` | `concise`, `balanced` or `detailed` |
| `ANSWER_STYLE_MAX_SECTIONS` | `4` | Heading budget for balanced answers |

### Backend API additions
| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/chats/{chat_id}/messages/{message_id}/edit` | Owner | Replace a question, delete later messages, stream a new answer (SSE) |
| `POST /api/chats/{chat_id}/messages/{message_id}/share` | Owner | Create or refresh the public link for a question; returns `{token}` |
| `GET /api/shared/prompts/{token}` | Public | Read a shared question |

The answer stream now also starts with a `{"type": "user_message", "message_id": ...}` event so the page knows the saved ID of the question being answered.

**Database:** a new `shared_prompts` table is created automatically when the backend starts. Restart the backend after pulling these changes.

### Known limitations
* Formatting is guided by the prompt; the model can still occasionally add a table or a recap.
* Logged-out visitors who click "Ask Clyptus.AI" on a shared link go through login and lose the pre-filled question.
* Share links use the current host (`localhost` in development), so they only work for others once the app is deployed.
* The older sidebar "Share chat" option builds a link that nothing handles yet.

---

## 🧪 Running Automated Tests

Tests never touch the live database: `backend/tests/conftest.py` redirects them to `<database>_test` (`sap_brim_ai_test`) and refuses to run against any database whose name does not end in `_test`. Create it once as a clone of the live database (it also gives retrieval tests the real knowledge base); drop and re-create it to reset:

```bash
docker exec sap_assistant_postgres createdb -U sap_assistant -O sap_brim_ai -T sap_brim_ai sap_brim_ai_test
```

Run the backend test suite to verify system integrity:

```bash
# Run all offline tests (tests marked "live" call external LLM/web APIs)
python -m pytest backend/tests -m "not live" -v

# PostgreSQL migration regression tests (no-fallback, 503 handling, exact vectors, retrieval parity)
python -m pytest backend/tests/test_postgres_migration.py -v

# Run admin security and role-enforcement tests
python -m pytest backend/tests/test_admin_portal_security.py -v

# Run live streaming and source hiding verification
python -m pytest backend/tests/test_streaming_and_source_hiding.py -v

# Answer Style Router (offline; LLM and retrieval mocked)
python -m pytest backend/tests/test_answer_style_router.py -v

# Edit and share prompt endpoints
python -m pytest backend/tests/test_edit_prompt.py backend/tests/test_share_prompt.py -v
```

---

## 📦 Project Structure

```text
SAP_BRIM_Ai/
├── README.md                           # Master setup and architecture documentation
├── docker-compose.yml                  # PostgreSQL + pgvector container (the only database)
├── .env.example                        # Compose settings template (ports, DB passwords)
├── docker/postgres/init/               # First-start script: sap_brim_ai role, database, vector extension
├── pytest.ini                          # Pytest configuration
│
├── backend/                            # FastAPI Backend Service
│   ├── .env.example                    # Environment variable template (DATABASE_URL, API keys)
│   ├── requirements.txt                # Python dependencies
│   ├── scripts/migrate_sqlite_to_pgvector.py  # One-time SQLite cutover utility (backup/migrate/verify)
│   │
│   ├── app/                            # Application Core
│   │   ├── main.py                     # FastAPI entrypoint and route mounting
│   │   ├── config.py                   # Pydantic application settings & feature flags
│   │   ├── database.py                 # PostgreSQL engine, schema/index setup, auto-seeding
│   │   ├── api/                        # API routes (auth, chats, messages, documents, rag_inspect)
│   │   ├── models/                     # SQLAlchemy models (User, Chat, Message, Document, Chunk)
│   │   ├── schemas/                    # Pydantic validation schemas
│   │   ├── security/                   # JWT authentication, password hashing, role guards
│   │   ├── services/                   # RAG service, LLM streaming failover, document extractor
│   │   └── retrieval/                  # Multi-source comparator, BM25 + dense search
│   │
│   └── tests/                          # Automated Pytest test suite
│
├── frontend/                           # React 19 + TypeScript + Vite Web Client
│   ├── package.json                    # Frontend dependencies
│   ├── vite.config.ts                  # Vite build and proxy config
│   ├── tailwind.config.js              # Tailwind styling
│   │
│   └── src/                            # Application Source Code
│       ├── main.tsx                    # React client entrypoint
│       ├── App.tsx                     # Application router and layout
│       ├── components/                 # Reusable UI components (chat, markdown, badges)
│       ├── context/                    # AuthContext and state providers
│       ├── layouts/                    # AppLayout, AdminProtectedRoute
│       ├── pages/                      # Page views (ChatPage, LandingPage, AdminDashboard, AdminLoginPage)
│       └── services/                   # SSE streaming client and REST API service calls
│
└── knowledge_base/                     # Canonical SAP BRIM PDF documents repository
    └── documents/                      # Pre-indexed courseware, guides, and SAP Press books
```

---

## 🛠️ Troubleshooting & FAQs

### 1. `Port 8000 or 5173 already in use`
* **Windows**: Open Task Manager or run:
  ```powershell
  Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process -Force
  ```
* **macOS/Linux**:
  ```bash
  lsof -ti :8000 | xargs kill -9
  ```

### 2. Backend exits with `DATABASE UNAVAILABLE` / `Cannot connect to PostgreSQL`
1. Follow section F above to check Docker, the container, `pg_isready`, and host port 5434.
2. Check that `DATABASE_URL` in `backend/.env` targets `sap_brim_ai` at `127.0.0.1:5434` and that its password matches root `SAP_BRIM_DB_PASSWORD`.
3. If Docker reports a read-only filesystem, I/O error, or missing `runc`, treat it as an engine/storage failure; do not remove the container or volume as a troubleshooting shortcut.

### 3. Frontend fails to connect to backend
Ensure the backend server is running on `http://127.0.0.1:8000`. The Vite development server automatically proxies `/api/*` requests to port `8000`.

---

## 🗄️ Database: PostgreSQL + pgvector

| Setting | Value |
| :--- | :--- |
| Container / image | `sap_assistant_postgres` / `pgvector/pg16` (installed extension version not verified in this session) |
| Volume | `sap_brim_pgdata` (verified attached to this checkout's container) |
| Host port | `127.0.0.1:5434` → container `5432` |
| Application database / role | `sap_brim_ai` / `sap_brim_ai` |
| Test database | `TEST_DATABASE_URL` must name a database ending in `_test` (guarded by `backend/tests/conftest.py`) |
| Vector column | `document_chunks.embedding vector(384)` + HNSW index (`vector_cosine_ops`) + GIN full-text index |

See section G above for the PowerShell backup and non-overwriting restore procedure. It has not been run against the current database because Docker cannot start its container.

### Migration from SQLite (2026-10-16)

The knowledge base previously lived in `backend/sap_assistant.db` (SQLite). It was migrated with `backend/scripts/migrate_sqlite_to_pgvector.py`, which:
1. took a consistent backup and manifest (`backups/sqlite/`),
2. copied all 11 tables in one transaction with `ON CONFLICT (id) DO NOTHING` duplicate protection, transferring the existing embeddings verbatim (no re-embedding, re-chunking or re-ingestion),
3. verified every row and column, and every vector component for exact float32 equality, plus foreign keys and delete cascade.

The original `backend/sap_assistant.db` and its backup are kept until their deletion is explicitly authorised. Logs and reports are in `backups/migration_logs/`.

The SQLite cutover and rollback notes in the original README described historical code that has since been removed. The current application requires PostgreSQL; do not apply the old reverse patch or point `DATABASE_URL` at an invalid host to trigger a fallback.

---

## 📄 License
Proprietary & Confidential. All rights reserved by **Clyptus-Soft**.


How it works now
One plan per question. A new router, answer_style_router.py, decides the layout once, after evidence is selected. The same plan is used for the streamed answer, the fallback answer and any repair. It picks one of the six styles you specified (direct answer, explanation, comparison, steps, troubleshooting, document research), a detail level, whether a table or numbered steps fit, and a maximum number of headings.
Rules first. It builds on the planner's existing question categories, plus checks for explicit requests ("in a table", "without a table", "briefly", "step by step", bullets), how-to vs how-does wording, comparisons, error reports, document questions and short factual questions.
LLM only for unclear questions. Questions the rules can't place get one small, fast call to the Groq model openai/gpt-oss-20b. The result is checked against a strict schema and cached. If the call fails or returns anything invalid, the answer uses a balanced explanation.
Prompts. For most question types, a short format instruction replaces the rigid section templates, together with the formatting rules from your spec. Upgrade/reconciliation and business-partner block questions keep their structured templates, because those carry safety content.
Grounding is unchanged. Claim verification, repair, the safety guard and citation rules run exactly as before. When both internal documents and web results are used, the model is told to say which statements come from the web.
The plan stays internal. It is stored only in the admin-only audit data and is never streamed, so the SSE events are unchanged.
Frontend: headings now have sizes, h4 is styled, and table cells are top-aligned. Lists, code and table scrolling already rendered correctly.
Example answers (live runs against your dev database, web search off)
Before (router off): a 5-row table with whole paragraphs inside the cells. It explained aggregation twice, then added separate "Component" and "Release" blocks.
After: one direct sentence, three workflow bullets citing [E1]–[E5], and a one-line note on what the evidence doesn't cover.
Comparison (CI vs FI-CA): a one-sentence summary of the difference, a 3-row table with short cells, the key differences, and a conclusion.
Troubleshooting (billable items stuck in raw status): the cause labelled "Suspected", 7 numbered diagnostic steps, the fix, and verification steps.
The early live runs showed two leftovers, and I've fixed both in the prompts:

Recap sections: answers ended with "Key points" sections that repeated earlier content.
Invalid citation markers: the model wrote markers like [All evidence] and [E1-E5], which aren't real evidence IDs and aren't stripped for regular users.
Tests
New tests: I added test_answer_style_router.py with 31 offline tests, all passing. They cover your 14 cases plus caching, the planner fix and turning the router off. Case 11 runs the real streaming pipeline with retrieval and the LLM mocked.
Full backend suite: 239 passed and 8 failed. The 8 are the same ones that were already failing (6 document-dashboard tests plus test_integration_real_retriever_and_chunk_uuids and test_file_filtering_skips_binaries_and_lockfiles).
Frontend: the type check and build pass.
Configuration
Seven new settings in config.py, all with working defaults, so .env changes are optional:

Setting	Default
ANSWER_STYLE_ROUTER_ENABLED	True (set False to go back to the old template prompts)
ANSWER_STYLE_LLM_CLASSIFIER_ENABLED	True
ANSWER_STYLE_CLASSIFIER_MODEL	openai/gpt-oss-20b
ANSWER_STYLE_CLASSIFIER_TIMEOUT	4.0 seconds
ANSWER_STYLE_DEFAULT	technical_explanation
ANSWER_STYLE_DEFAULT_DETAIL	balanced
ANSWER_STYLE_MAX_SECTIONS	4
Limitations
Prompt guidance only. The model can still occasionally add a table or a recap. I didn't add an automatic rewrite step afterwards, because it could drop citations.
Most tests check prompts and routing, not live answers. The live runs above are the only check of actual output.
Other tests may hit the classifier live. Some existing pipeline tests call the real LLM, so an ambiguous question in them may trigger one classifier call.
A transaction question was refused. "What is transaction FKKBIXBIT_MON used for?" was turned down by the existing SAP topic check before reaching the router. That's unrelated to this change.
Other edits: I widened three test fakes in test_bp_block_regression.py to accept the new argument, and fixed the planner's error-word matching.
