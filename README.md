# SAP Knowledge Assistant & Admin Portal

An enterprise-grade **SAP Knowledge Assistant** powered by Retrieval-Augmented Generation (RAG) with strict domain boundaries, verifiable citations, and a developer-managed knowledge base.

---

## 🚀 Live Application URLs

When running locally, access the services at:

- **Frontend Application (Web Portal):** [http://localhost:5173](http://localhost:5173)
- **Backend API Root:** [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Backend Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 📌 Prerequisites

Ensure you have the following installed on your machine:
- **Python**: Version `3.10` or higher (verified with Python 3.14)
- **Node.js**: Version `18.0` or higher & **npm**
- *(Optional)* **Docker & Docker Compose**: If you want to run PostgreSQL with `pgvector` instead of the built-in SQLite database.

---

## ⚡ Quick Start: Running Commands

### 1. Clone & Open the Repository
```bash
git clone https://github.com/Eshwar12reddy/SAP_Project.git
cd SAP_Project
```

---

### 2. Backend Setup & Run

Open a terminal in the `SAP_Project` root directory:

#### Step A: Install Python Dependencies
```bash
pip install -r requirements.txt
```

#### Step B: Configure Environment Variables
Copy the example `.env` file (if not already created):
```bash
cp backend/.env.example backend/.env
```
*(On Windows PowerShell, use `copy backend\.env.example backend\.env`)*

#### Step C: Start the FastAPI Backend Server
Run from the `SAP_Project` root directory:
```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

> **Note on Database**: The backend automatically attempts to connect to PostgreSQL. If PostgreSQL is not running, it gracefully falls back to the local SQLite database (`backend/sap_assistant.db`), requiring **zero manual configuration** to start.

---

### 3. Frontend Setup & Run

Open a second terminal and navigate to the `frontend` folder:

#### Step A: Navigate to frontend directory
```bash
cd frontend
```

#### Step B: Install Node Dependencies
```bash
npm install
```

#### Step C: Start the Frontend Development Server
```bash
npm run dev
```

The frontend will start at **[http://localhost:5173](http://localhost:5173)** and automatically proxy `/api` requests to the backend at port 8000.

---

## 🛠️ Additional Useful Commands

### Running the Test Suite
From the `SAP_Project` root folder:
```bash
python -m pytest backend/tests
```

### Ingesting Documents into the Vector / Knowledge Base
To parse PDFs in `knowledge_base/documents` and generate chunk embeddings:
```bash
python -m backend.app.ingestion.ingest
```

### Generating SAP Reference Documentation PDFs
To generate the 10 core SAP reference manuals in PDF format:
```bash
python backend/generate_sap_docs.py
```

### Optional: Running PostgreSQL with pgvector via Docker
If you want full PostgreSQL vector similarity search instead of SQLite:
```bash
docker compose up -d
```
Update `DATABASE_URL` in `backend/.env` to:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sap_assistant
```

---

## ⚙️ Configuration Reference (`backend/.env`)

| Variable | Default Value | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/sap_assistant` | PostgreSQL connection string (falls back to SQLite if unreachable) |
| `JWT_SECRET` | `sap-super-secret-jwt-key-2026-production-ready` | Secret key for signing user authentication tokens |
| `ADMIN_API_KEY` | `sap-admin-dev-secret-key-999` | Secret key for developer-level ingestion APIs |
| `LLM_PROVIDER` | `openai` | LLM provider: `openai`, `groq`, or `local` |
| `LLM_API_KEY` | *(Optional)* | API Key for OpenAI or cloud LLM |
| `GROQ_API_KEY` | *(Optional)* | API Key for Groq Cloud LLM |
| `EMBEDDING_MODEL`| `all-MiniLM-L6-v2` | SentenceTransformer model for dense embeddings |
| `WEB_FALLBACK_ENABLED`| `True` | Whether to perform web fallback for external topics |
| `WEB_SEARCH_API_KEY` | *(Optional)* | Tavily API Key for live web fallback retrieval |

---

## 📁 Project Structure

```
SAP_Project/
├── backend/
│   ├── app/
│   │   ├── api/            # API Endpoints (Auth, Chats, Messages, RAG, Admin)
│   │   ├── ingestion/      # Document ingestion & chunking pipeline
│   │   ├── models/         # SQLAlchemy database models
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── security/       # JWT auth & password hashing
│   │   ├── services/       # RAG, LLM, Embedding, Classification services
│   │   ├── config.py       # Pydantic Settings
│   │   ├── database.py     # Database engine & session management
│   │   └── main.py         # FastAPI application entry point
│   ├── generate_sap_docs.py# Script to generate SAP PDF documentation
│   ├── sap_assistant.db    # Pre-populated SQLite knowledge database
│   ├── tests/              # Pytest test suite
│   ├── .env.example        # Environment variable template
│   └── requirements.txt    # Python dependencies
├── frontend/
│   ├── src/                # React components and pages
│   ├── package.json        # Frontend dependencies and scripts
│   └── vite.config.ts      # Vite config with /api proxy to localhost:8000
├── docker-compose.yml      # Optional pgvector PostgreSQL container
├── requirements.txt        # Root-level Python dependencies
└── README.md               # Project documentation and running guide
```
