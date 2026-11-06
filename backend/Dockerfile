# Backend API image: FastAPI + uvicorn on Python 3.12. Used by docker-compose.prod.yml (see DEPLOYMENT.md).
# Build context is the repository root:
#   docker build -f backend/Dockerfile -t sap-brim-backend .
# Configuration comes from environment variables (docker compose passes the root .env); no .env file is
# copied into the image (.dockerignore).
FROM python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache

# Runtime libraries for the OCR (OpenCV / ONNX Runtime) and PyTorch wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Reproducible install: backend/requirements.lock pins every package (Linux, Python 3.12) with hashes and
# uses the CPU-only PyTorch build (the CUDA build adds several GB; the backend never uses a GPU).
# Regenerate after changing backend/requirements.txt (see DEPLOYMENT.md, "Dependencies").
RUN pip install --upgrade "pip>=26.2"
COPY backend/requirements.lock backend/requirements.lock
RUN pip install --require-hashes --no-deps --only-binary :all: \
      --extra-index-url https://download.pytorch.org/whl/cpu -r backend/requirements.lock \
 && pip check

# Bake the models into the image so containers start without downloading them and the unprivileged user
# never has to write into site-packages:
# - the embedding model; it must equal EMBEDDING_MODEL in .env (stored vectors record the model name);
# - RapidOCR's ONNX models (image and scanned-PDF text), which it otherwise fetches into its package folder.
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
RUN python -c "import sys; from sentence_transformers import SentenceTransformer; SentenceTransformer(sys.argv[1])" "$EMBEDDING_MODEL" \
 && python -c "from rapidocr import RapidOCR; RapidOCR()" \
 && chmod -R a+rwX "$HF_HOME"
# The baked model is the only Hugging Face download the backend needs; skip the hub check at start.
# Changing EMBEDDING_MODEL therefore needs an image rebuild (`docker compose ... up -d --build`).
ENV HF_HUB_OFFLINE=1

COPY backend/ backend/

# Unprivileged user. APP_UID should own ./knowledge_base on the host (bind-mounted for admin uploads);
# 1000 is the first user on most Linux servers. Check with `id -u`.
ARG APP_UID=1000
RUN useradd --uid "$APP_UID" --user-group --home-dir /app --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /app/knowledge_base/documents \
 && chown -R app:app /app/knowledge_base
USER app

EXPOSE 8000

# /health answers over plain HTTP even with ENVIRONMENT=production (it reveals nothing).
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# Apply database migrations, then serve. One worker: rate limits, login lockout and answers that keep
# generating after the browser leaves are tracked per process (see DEPLOYMENT.md before scaling out).
# Set RUN_MIGRATIONS_ON_START=false to run `python -m alembic -c backend/alembic.ini upgrade head` yourself.
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS_ON_START:-true}\" = \"true\" ]; then python -m alembic -c backend/alembic.ini upgrade head; fi && exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1 --timeout-graceful-shutdown 30"]
