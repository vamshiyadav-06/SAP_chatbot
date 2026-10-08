import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "SAP Knowledge Assistant"
    API_V1_STR: str = "/api"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5434/sap_assistant"
    )
    # If postgresql fails, fallback to local sqlite for zero-friction development
    SQLITE_FALLBACK_URL: str = f"sqlite:///{BASE_DIR / 'sap_assistant.db'}"

    # JWT Security
    JWT_SECRET: str = os.getenv("JWT_SECRET", "sap-super-secret-jwt-key-2026-production-ready")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Admin Key for Developer Ingestion
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "sap-admin-dev-secret-key-999")

    # LLM Settings
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")  # openai, groq, or local
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # Embedding & RAG parameters
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = 384
    TOP_K: int = int(os.getenv("TOP_K", "50"))
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "8"))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.60"))
    GROUNDING_THRESHOLD: float = float(os.getenv("GROUNDING_THRESHOLD", "0.65"))

    # Web Fallback
    WEB_FALLBACK_ENABLED: bool = os.getenv("WEB_FALLBACK_ENABLED", "True").lower() in ("true", "1")
    WEB_SEARCH_API_KEY: str = os.getenv("WEB_SEARCH_API_KEY", "")

    # Canonical Knowledge Base Paths (at repo root if exists, otherwise backend)
    KNOWLEDGE_BASE_DIR: Path = (ROOT_DIR / "knowledge_base") if (ROOT_DIR / "knowledge_base").exists() else (BASE_DIR / "knowledge_base")
    DOCUMENTS_DIR: Path = (ROOT_DIR / "knowledge_base" / "documents") if (ROOT_DIR / "knowledge_base" / "documents").exists() else (BASE_DIR / "knowledge_base" / "documents")

    model_config = SettingsConfigDict(
        env_file=(
            str(BASE_DIR / ".env")
            if (BASE_DIR / ".env").exists()
            else (
                str(BASE_DIR / "app" / ".env")
                if (BASE_DIR / "app" / ".env").exists()
                else str(ROOT_DIR / ".env")
            )
        ),
        extra="allow"
    )

settings = Settings()

