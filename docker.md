# Database Access Guide (Docker · PostgreSQL + pgvector)

All application data lives in **PostgreSQL with the pgvector extension, running in Docker**: documents, chunks, 384-dimension embeddings, users, chats, messages and citations. There is no other database and no fallback.

The backend and frontend run on your machine (not in Docker) and connect to this database over `127.0.0.1:5434`. For full PowerShell startup, health-check, troubleshooting, and backup instructions, use the [main README](README.md).

---

## 1. Connection details

| Setting | Value |
| :--- | :--- |
| Container | `sap_assistant_postgres` |
| Image | `pgvector/pg16` (PostgreSQL 16; installed extension version not verified in this session) |
| Host / port (from your machine) | `127.0.0.1` / `5434` |
| Host / port (from another container on the same Compose network) | `postgres` / `5432` |
| Database | `sap_brim_ai` |
| User | `sap_brim_ai` |
| Password | The password is in `DATABASE_URL` in `backend/.env`, and also in `SAP_BRIM_DB_PASSWORD` in the root `.env`. Both files are git-ignored; ask the project owner if you don't have them. |
| Data volume | `sap_brim_pgdata` |

Connection URL format:

```
postgresql://sap_brim_ai:<password>@127.0.0.1:5434/sap_brim_ai
```

The port is bound to `127.0.0.1` only, so the database can be reached from this computer but not from other machines on the network.

---

## 2. Start, stop and check the database

Run these from the repository root (`SAP_BRIM_Ai`).

```bash
# Start (or confirm it is running)
docker compose up -d postgres

# Check status: it should say "healthy"
docker ps --filter name=sap_assistant_postgres

# View logs
docker logs --tail 50 sap_assistant_postgres

# Stop (data is kept)
docker compose stop postgres
```

The first time on a new machine, copy `.env.example` to `.env` and set the passwords before running `docker compose up` (see the README, Step 2).

---

## 3. Open a SQL shell (quickest way)

You don't need a password for this, because it connects from inside the container:

```bash
docker exec -it sap_assistant_postgres psql -U sap_brim_ai -d sap_brim_ai
```

Useful `psql` commands once you're inside:

| Command | What it does |
| :--- | :--- |
| `\dt` | List tables |
| `\d document_chunks` | Show a table's columns and indexes |
| `\x auto` | Readable layout for wide rows |
| `\q` | Quit |

To run a single query without opening the shell:

```bash
docker exec sap_assistant_postgres psql -U sap_brim_ai -d sap_brim_ai -c "SELECT COUNT(*) FROM document_chunks;"
```

---

## 4. Connect with a GUI tool (pgAdmin, DBeaver, DataGrip, VS Code)

Create a new PostgreSQL connection with these values:

- **Host:** `127.0.0.1`
- **Port:** `5434`
- **Database:** `sap_brim_ai`
- **Username:** `sap_brim_ai`
- **Password:** from `backend/.env` (see section 1)
- **SSL:** disable / not required

To use the `psql` client installed on your own machine instead:

```bash
psql "postgresql://sap_brim_ai:<password>@127.0.0.1:5434/sap_brim_ai"
```

---

## 5. What's in the database

| Table | Contents |
| :--- | :--- |
| `documents` | One row per knowledge-base file (filename, title, page count, status) |
| `document_chunks` | Text chunks with page/section, metadata, `embedding vector(384)` and `insertion_order` |
| `users` | Application accounts (passwords are stored as bcrypt hashes) |
| `chats`, `messages` | Chat history |
| `citations`, `web_sources`, `web_images` | Sources attached to assistant answers |
| `uploaded_attachments` | Text extracted from files users attach in chat |
| `github_repo_chunks`, `web_doc_chunks` | Optional extra vector sources (empty unless enabled) |

Deleting a document automatically deletes its chunks and vectors (foreign key `ON DELETE CASCADE`).

---

## 6. Example queries (read-only)

```sql
-- Row counts
SELECT
  (SELECT COUNT(*) FROM documents)       AS documents,
  (SELECT COUNT(*) FROM document_chunks) AS chunks,
  (SELECT COUNT(*) FROM users)           AS users,
  (SELECT COUNT(*) FROM chats)           AS chats;

-- Documents with their chunk counts
SELECT d.filename, d.page_count, d.status, COUNT(c.id) AS chunks
FROM documents d
LEFT JOIN document_chunks c ON c.document_id = d.id
GROUP BY d.id
ORDER BY chunks DESC;

-- Read chunks of one document
SELECT chunk_index, page_number, section, LEFT(chunk_text, 200) AS preview
FROM document_chunks
WHERE document_name = 'SAP CC.pdf'
ORDER BY chunk_index
LIMIT 10;

-- Keyword search
SELECT document_name, page_number, LEFT(chunk_text, 150) AS preview
FROM document_chunks
WHERE chunk_text ILIKE '%DFKKBIXBIT%'
LIMIT 10;

-- Inspect embeddings (the full vector is long, so show its size and start)
SELECT id, vector_dims(embedding) AS dims, LEFT(embedding::text, 80) AS vector_start
FROM document_chunks
LIMIT 3;

-- Vector similarity: the 5 chunks closest to an existing chunk (cosine distance)
SELECT c.document_name, c.page_number,
       ROUND((1 - (c.embedding <=> q.embedding))::numeric, 4) AS cosine_similarity,
       LEFT(c.chunk_text, 120) AS preview
FROM document_chunks c,
     (SELECT embedding FROM document_chunks ORDER BY insertion_order LIMIT 1) q
ORDER BY c.embedding <=> q.embedding
LIMIT 5;

-- Recent chat activity
SELECT u.email, ch.title, ch.updated_at
FROM chats ch JOIN users u ON u.id = ch.user_id
ORDER BY ch.updated_at DESC
LIMIT 10;
```

pgvector operators: `<=>` is cosine distance, `<->` is Euclidean (L2) distance and `<#>` is negative inner product. Smaller values mean more similar.

---

## 7. Access from Python

```python
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg2://sap_brim_ai:<password>@127.0.0.1:5434/sap_brim_ai")
with engine.connect() as conn:
    for row in conn.execute(text("SELECT filename, page_count FROM documents ORDER BY filename")):
        print(row.filename, row.page_count)
```

Inside the application, use the existing session instead: `from backend.app.database import SessionLocal`.

---

## 8. Backup and restore

Use the guarded PowerShell backup and restore procedure in [README section G](README.md#g-database-backup-and-recovery). It restores into a separate empty database and never overwrites the current target.

In Git Bash on Windows, run `export MSYS_NO_PATHCONV=1` first; otherwise it rewrites `/tmp/...` into a Windows path.

---

## 9. Test database

Automated tests use a separate copy called `sap_brim_ai_test`, never the live database. To create or reset it:

```bash
docker exec sap_assistant_postgres dropdb -U sap_assistant --if-exists sap_brim_ai_test
docker exec sap_assistant_postgres createdb -U sap_assistant -O sap_brim_ai -T sap_brim_ai sap_brim_ai_test
```

`createdb -T` copies the live database, so stop the backend first (the copy fails while other connections to `sap_brim_ai` are open).

---

## 10. Safety rules

- **Never run `docker compose down -v`.** The `-v` deletes the data volume, and with it every database in the container.
- This application uses the `sap_brim_ai` database; `sap_assistant` is the Compose bootstrap database/account.
- PostgreSQL for this project is bound to `127.0.0.1:5434`; ignore stale port 5435 instructions.
- Prefer read-only `SELECT` queries. To change data, go through the application or take a backup first (section 8).
- Never commit `.env` or `backend/.env`; they contain the passwords.

---

## 11. Troubleshooting

| Problem | Fix |
| :--- | :--- |
| `connection refused` on port 5434 | Check Docker Desktop and `docker compose ps`, then inspect the container and port mapping before starting services. |
| `password authentication failed` | Copy the password exactly from `DATABASE_URL` in `backend/.env`. |
| `docker compose up` says `POSTGRES_PASSWORD` / `SAP_BRIM_DB_PASSWORD` must be set | Create `.env` in the repository root from `.env.example`. |
| Backend exits with `DATABASE UNAVAILABLE` | The database isn't running or `DATABASE_URL` is wrong. Check with `docker ps` and section 1. |
| `database "sap_brim_ai" does not exist` on a new machine | The init script only runs on a new, empty volume. Create the role and database manually (replace `<password>`):<br>`docker exec sap_assistant_postgres psql -U sap_assistant -d postgres -c "CREATE ROLE sap_brim_ai LOGIN PASSWORD '<password>';"`<br>`docker exec sap_assistant_postgres createdb -U sap_assistant -O sap_brim_ai sap_brim_ai`<br>`docker exec sap_assistant_postgres psql -U sap_assistant -d sap_brim_ai -c "CREATE EXTENSION IF NOT EXISTS vector;"` |

---

## 12. Self-Hosted Search Services (SearXNG & Siftdog)

The Docker Compose stack also manages self-hosted search and retrieval services:

| Service | Container | Image | Port | Description |
| :--- | :--- | :--- | :--- | :--- |
| **SearXNG** | `sap_assistant_searxng` | `searxng/searxng:latest` | `8089` | Metasearch engine with multi-engine web & image discovery |
| **Siftdog** | `sap_assistant_siftdog` | `ghcr.io/khsarvar/siftdog:latest` | `8088` | Search, clean extraction, crawling, and site mapping API |

Start search services:
```bash
docker compose up -d searxng siftdog
```

Health check:
```bash
curl http://127.0.0.1:8088/health
curl "http://127.0.0.1:8089/search?q=test&format=json"
```

For full architecture and API details, refer to [the SearXNG/Siftdog integration guide](docs/SEARXNG_SIFTDOG_INTEGRATION.md).
