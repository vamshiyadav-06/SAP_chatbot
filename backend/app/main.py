import logging
from contextlib import asynccontextmanager
import jwt
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.app.config import settings, security_settings_errors
from backend.app.security.auth import decode_access_token
from backend.app.security.ratelimit import client_ip, rate_limiter, warn_if_not_shared
from backend.app.security.log_safety import PrivacyLogFilter
from backend.app.security.body_size import BodyTooLarge, RequestBodySizeLimitMiddleware
from backend.app.database import init_db, SessionLocal, DatabaseConnectionError, describe_target
from backend.app.api.auth import router as auth_router
from backend.app.api.chats import router as chats_router
from backend.app.api.messages import router as messages_router
from backend.app.api.rag import router as rag_router
from backend.app.api.admin import router as admin_router
from backend.app.api.rag_inspect import router as rag_inspect_router
from backend.app.api.documents import router as documents_router
from backend.app.api.shared import router as shared_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_root_logger = logging.getLogger()
if not any(isinstance(item, PrivacyLogFilter) for handler in _root_logger.handlers for item in handler.filters):
    for _handler in _root_logger.handlers:
        _handler.addFilter(PrivacyLogFilter())
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
    warn_if_not_shared()
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

_production = settings.ENVIRONMENT.lower() == "production"

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Enterprise SAP Knowledge Assistant with Developer-Managed RAG and Strict Domain Boundaries",
    version="1.0.0",
    lifespan=lifespan,
    # The API description is not published in production (AUDIT_REPORT F-42).
    docs_url=None if _production else "/docs",
    redoc_url=None if _production else "/redoc",
    openapi_url=None if _production else "/openapi.json",
)

def _rate_limit_identity(request: Request) -> str:
    """A signature-verified user id, otherwise the client IP. Never the raw Authorization header:
    any random header value would otherwise open a fresh bucket (AUDIT_REPORT F-06)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            return f"user:{decode_access_token(auth[7:])['sub']}"
        except jwt.PyJWTError:
            pass
    return f"ip:{client_ip(request)}"


def _rate_limit_scope(request: Request):
    path = request.url.path
    if path.startswith("/api/auth/"):
        return "auth", settings.AUTH_RATE_LIMIT_PER_MINUTE
    if path.endswith("extract-document"):
        return "extract", settings.EXTRACT_RATE_LIMIT_PER_MINUTE
    if path.startswith("/api/rag/") or ("/messages" in path and request.method == "POST"):
        # One budget for all answer endpoints and chats, so new chats do not reset it.
        return "answer", settings.ANSWER_RATE_LIMIT_PER_MINUTE
    return None, None


@app.middleware("http")
async def request_security_controls(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            body_limit = settings.MAX_TOTAL_UPLOAD_BYTES + 1024 * 1024 if request.url.path == "/api/documents/upload" else settings.MAX_REQUEST_BODY_BYTES
            if int(content_length) > body_limit:
                return JSONResponse(status_code=413, content={"detail": "Request body too large."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid content length."})
    scope, limit = _rate_limit_scope(request)
    if scope and not rate_limiter.allow(scope, _rate_limit_identity(request), limit, 60):
        logger.warning("security_event rate_limit scope=%s", scope)
        return JSONResponse(status_code=429, content={"detail": "Too many requests. Try again shortly."})
    return await call_next(request)


DOCS_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}


@app.middleware("http")
async def browser_security_headers(request: Request, call_next):
    # Behind a TLS-terminating proxy the scheme comes from X-Forwarded-Proto, believed only from
    # TRUSTED_PROXIES (ProxyHeadersMiddleware, outermost). /health stays reachable over plain HTTP for
    # container and load-balancer probes; it reveals nothing (F-41, F-42).
    if (settings.ENVIRONMENT.lower() == "production" and request.url.scheme != "https"
            and request.url.path != "/health"):
        return JSONResponse(status_code=400, content={"detail": "HTTPS is required."})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path not in DOCS_PATHS:
        # API responses are data, never pages: nothing may run or be framed, and nothing (answers,
        # chat history, tokens) may be stored by browsers or shared caches (AUDIT_REPORT F-26).
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("Pragma", "no-cache")
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

# Outermost: resolve the real client IP and scheme before rate limiting and the HTTPS check, believing
# X-Forwarded-* only from the configured reverse proxies (AUDIT_REPORT F-06, F-41).
_trusted_proxies = [p.strip() for p in settings.TRUSTED_PROXIES.split(",") if p.strip()]
app.add_middleware(
    RequestBodySizeLimitMiddleware,
    default_limit=settings.MAX_REQUEST_BODY_BYTES,
    upload_limit=settings.MAX_TOTAL_UPLOAD_BYTES + 1024 * 1024,
)
if _trusted_proxies:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=_trusted_proxies)

DATABASE_UNAVAILABLE_DETAIL = "Database unavailable: the PostgreSQL server cannot be reached. Please try again shortly."


@app.exception_handler(BodyTooLarge)
async def request_body_too_large_handler(request: Request, exc: BodyTooLarge):
    return JSONResponse(status_code=413, content={"detail": "Request body too large."})


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
    """Liveness and database reachability only. Counts, model and version are admin-only
    (GET /api/admin/system-health) so anonymous callers learn nothing about the corpus (F-42)."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": {"status": "connected"}}
    except OperationalError as exc:
        logger.error(f"Health check: PostgreSQL unreachable at {describe_target(settings.DATABASE_URL)}: {exc.orig}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": {"status": "unavailable"}, "detail": DATABASE_UNAVAILABLE_DETAIL},
        )
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
