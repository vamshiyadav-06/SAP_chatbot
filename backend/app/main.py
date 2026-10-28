import logging
import hashlib
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from backend.app.config import settings, security_settings_errors
from backend.app.database import init_db, SessionLocal, DatabaseConnectionError, describe_target
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.api.auth import router as auth_router
from backend.app.api.chats import router as chats_router
from backend.app.api.messages import router as messages_router
from backend.app.api.rag import router as rag_router
from backend.app.api.admin import router as admin_router
from backend.app.api.rag_inspect import router as rag_inspect_router
from backend.app.api.documents import router as documents_router
from backend.app.api.shared import router as shared_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    insecure = security_settings_errors()
    if insecure:
        for problem in insecure:
            logger.critical("INSECURE CONFIGURATION - backend not started. %s", problem)
        raise RuntimeError("Insecure configuration in backend/.env: " + " ".join(insecure))
    if settings.ENVIRONMENT.lower() == "production" and (
        not settings.ALLOWED_ORIGINS.strip()
        or "*" in settings.ALLOWED_ORIGINS
        or any("localhost" in origin or "127.0.0.1" in origin for origin in settings.ALLOWED_ORIGINS.split(","))
    ):
        raise RuntimeError("Production requires explicit public ALLOWED_ORIGINS without wildcards or localhost entries.")
    logger.info("Initializing database and verifying tables...")
    try:
        init_db()
    except DatabaseConnectionError as exc:
        # No fallback database: refuse to start with a clear, actionable message.
        logger.critical("DATABASE UNAVAILABLE - backend not started. %s", exc)
        raise
    logger.info("SAP Knowledge Assistant backend ready.")
    yield
    logger.info("Shutting down SAP Knowledge Assistant backend.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Enterprise SAP Knowledge Assistant with Developer-Managed RAG and Strict Domain Boundaries",
    version="1.0.0",
    lifespan=lifespan
)

_rate_buckets = defaultdict(deque)


@app.middleware("http")
async def request_security_controls(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > 12 * 1024 * 1024:
                return JSONResponse(status_code=413, content={"detail": "Request body too large."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid content length."})
    path = request.url.path
    if path.startswith("/api/auth/"):
        limit = 8
    elif path.endswith("extract-document"):
        limit = 10
    elif path.startswith("/api/rag/") or ("/messages" in path and request.method == "POST"):
        limit = 12
    else:
        limit = None
    if limit:
        identity = request.headers.get("authorization", "") or (request.client.host if request.client else "unknown")
        key = (path, hashlib.sha256(identity.encode()).hexdigest())
        now = time.monotonic()
        bucket = _rate_buckets[key]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= limit:
            logger.warning("security_event rate_limit path=%s", path)
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Try again shortly."})
        bucket.append(now)
    return await call_next(request)


@app.middleware("http")
async def browser_security_headers(request: Request, call_next):
    if settings.ENVIRONMENT.lower() == "production" and request.url.scheme != "https":
        return JSONResponse(status_code=400, content={"detail": "HTTPS is required."})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.ENVIRONMENT.lower() == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_UNAVAILABLE_DETAIL = "Database unavailable: the PostgreSQL server cannot be reached. Please try again shortly."


# PostgreSQL went away after startup: report it explicitly instead of a generic 500.
@app.exception_handler(OperationalError)
@app.exception_handler(DatabaseConnectionError)
async def database_unavailable_handler(request: Request, exc: Exception):
    logger.error(f"Database unavailable on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": DATABASE_UNAVAILABLE_DETAIL},
    )


# Global safe error handling: never leak stack traces to client
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact the administrator."}
    )

# Include routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(chats_router, prefix=settings.API_V1_STR)
app.include_router(messages_router, prefix=settings.API_V1_STR)
app.include_router(rag_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(rag_inspect_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(shared_router, prefix=settings.API_V1_STR)

@app.get("/", tags=["Info"])
def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "api": "/api"
    }

@app.get("/health", tags=["Health"])
def health_check():
    db = SessionLocal()
    try:
        doc_count = db.query(Document).count()
        chunk_count = db.query(DocumentChunk).count()
        return {
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": "1.0.0",
            "database": {"engine": "postgresql+pgvector", "status": "connected"},
            "knowledge_base": {
                "documents_count": doc_count,
                "chunks_count": chunk_count,
                "model": settings.EMBEDDING_MODEL
            }
        }
    except OperationalError as exc:
        logger.error(f"Health check: PostgreSQL unreachable at {describe_target(settings.DATABASE_URL)}: {exc.orig}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": settings.PROJECT_NAME,
                "version": "1.0.0",
                "database": {"engine": "postgresql+pgvector", "status": "unavailable"},
                "detail": DATABASE_UNAVAILABLE_DETAIL,
            },
        )
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
