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

    # Database: PostgreSQL + pgvector (Docker) is the only supported database.
    # Required; there is deliberately no default and no fallback database.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DATABASE_CONNECT_TIMEOUT: int = int(os.getenv("DATABASE_CONNECT_TIMEOUT", "5"))
    DATABASE_POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    DATABASE_MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))

    # JWT Security. Required: no default, so tokens are never signed with a public value.
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Admin Key for Developer Ingestion. Empty disables X-Admin-Key access.
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")

    # Super admin created on first start; an existing account's password is never overwritten.
    SUPER_ADMIN_EMAIL: str = os.getenv("SUPER_ADMIN_EMAIL", "")
    SUPER_ADMIN_PASSWORD: str = os.getenv("SUPER_ADMIN_PASSWORD", "")

    # LLM Settings
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openrouter")  # openrouter, groq, openai, or local
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    # Groq rejects a request whose prompt plus reserved output exceeds this (free tier: 8000 per model).
    GROQ_TOKENS_PER_MINUTE: int = int(os.getenv("GROQ_TOKENS_PER_MINUTE", "20000"))
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

    # Vision models that read chat image attachments (comma-separated, tried in order).
    # OCR-only reading is used when vision is disabled or every model fails.
    VISION_ENABLED: bool = os.getenv("VISION_ENABLED", "True").lower() in ("true", "1")
    VISION_GROQ_MODELS: str = os.getenv("VISION_GROQ_MODELS", "qwen/qwen3.8-27b")
    VISION_OPENROUTER_MODELS: str = os.getenv(
        "VISION_OPENROUTER_MODELS", "nvidia/nemotron-3.5-super-vl:free,google/gemma-4-31b-it:free"
    )
    VISION_TIMEOUT_SEC: float = float(os.getenv("VISION_TIMEOUT_SEC", "45"))

    # Embedding & RAG parameters
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = 384
    TOP_K: int = int(os.getenv("TOP_K", "50"))
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "4"))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.60"))
    GROUNDING_THRESHOLD: float = float(os.getenv("GROUNDING_THRESHOLD", "0.65"))

    # Evidence Confidence & Grounding Verification Settings (v2)
    INTERNAL_EVIDENCE_THRESHOLD: float = float(os.getenv("INTERNAL_EVIDENCE_THRESHOLD", "0.70"))
    # Search GitHub and approved SAP web sources whenever the best document match
    # falls below this calibrated relevance score.
    DOCUMENT_MATCH_THRESHOLD: float = float(os.getenv("DOCUMENT_MATCH_THRESHOLD", "0.80"))
    AUTO_MULTI_SOURCE_FALLBACK: bool = os.getenv("AUTO_MULTI_SOURCE_FALLBACK", "True").lower() in ("true", "1")
    ANSWER_GROUNDING_THRESHOLD: float = float(os.getenv("ANSWER_GROUNDING_THRESHOLD", "0.80"))
    MAX_GROUNDING_REPAIR_ATTEMPTS: int = int(os.getenv("MAX_GROUNDING_REPAIR_ATTEMPTS", "1"))
    FOLLOWUP_QUESTION_COUNT: int = int(os.getenv("FOLLOWUP_QUESTION_COUNT", "3"))
    TAVILY_MAX_RESULTS: int = int(os.getenv("TAVILY_MAX_RESULTS", "5"))
    TAVILY_MAX_IMAGES: int = int(os.getenv("TAVILY_MAX_IMAGES", "4"))

    # Answer Style Router: picks the answer layout (direct answer, explanation, comparison, steps,
    # troubleshooting, document research) before generation. Grounding rules are unaffected.
    ANSWER_STYLE_ROUTER_ENABLED: bool = os.getenv("ANSWER_STYLE_ROUTER_ENABLED", "True").lower() in ("true", "1")
    # One small LLM call, only for questions the rules cannot place.
    ANSWER_STYLE_LLM_CLASSIFIER_ENABLED: bool = os.getenv("ANSWER_STYLE_LLM_CLASSIFIER_ENABLED", "True").lower() in ("true", "1")
    ANSWER_STYLE_CLASSIFIER_MODEL: str = os.getenv("ANSWER_STYLE_CLASSIFIER_MODEL", "openai/gpt-oss-20b")
    ANSWER_STYLE_CLASSIFIER_TIMEOUT: float = float(os.getenv("ANSWER_STYLE_CLASSIFIER_TIMEOUT", "4.0"))
    ANSWER_STYLE_DEFAULT: str = os.getenv("ANSWER_STYLE_DEFAULT", "technical_explanation")
    ANSWER_STYLE_DEFAULT_DETAIL: str = os.getenv("ANSWER_STYLE_DEFAULT_DETAIL", "balanced")
    ANSWER_STYLE_MAX_SECTIONS: int = int(os.getenv("ANSWER_STYLE_MAX_SECTIONS", "4"))

    # Claim-level technical validation (new; additive to the existing grounding gate)
    TECHNICAL_CLAIM_VALIDATION_ENABLED: bool = os.getenv("TECHNICAL_CLAIM_VALIDATION_ENABLED", "True").lower() in ("true", "1")
    # Inline [E#] evidence markers next to claims (stripped for users who cannot see sources)
    INLINE_EVIDENCE_MARKERS_ENABLED: bool = os.getenv("INLINE_EVIDENCE_MARKERS_ENABLED", "True").lower() in ("true", "1")
    # Restriction/block scope classification and per-scope retrieval expansion
    RESTRICTION_SCOPE_ENABLED: bool = os.getenv("RESTRICTION_SCOPE_ENABLED", "True").lower() in ("true", "1")
    RESTRICTION_SCOPE_MAX_EXPANSIONS: int = int(os.getenv("RESTRICTION_SCOPE_MAX_EXPANSIONS", "5"))
    RESTRICTION_SCOPE_PASSAGES_PER_CATEGORY: int = int(os.getenv("RESTRICTION_SCOPE_PASSAGES_PER_CATEGORY", "1"))
    # Web evidence: extract claim-relevant passages from page content instead of snippets only
    WEB_RAW_CONTENT_ENABLED: bool = os.getenv("WEB_RAW_CONTENT_ENABLED", "True").lower() in ("true", "1")
    WEB_PASSAGE_MAX_CHARS: int = int(os.getenv("WEB_PASSAGE_MAX_CHARS", "1800"))
    # Confidence components (observable; overall score never overrides a failed critical claim)
    CONFIDENCE_WEIGHT_RETRIEVAL: float = float(os.getenv("CONFIDENCE_WEIGHT_RETRIEVAL", "0.15"))
    CONFIDENCE_WEIGHT_COVERAGE: float = float(os.getenv("CONFIDENCE_WEIGHT_COVERAGE", "0.20"))
    CONFIDENCE_WEIGHT_CLAIMS: float = float(os.getenv("CONFIDENCE_WEIGHT_CLAIMS", "0.35"))
    CONFIDENCE_WEIGHT_AUTHORITY: float = float(os.getenv("CONFIDENCE_WEIGHT_AUTHORITY", "0.10"))
    CONFIDENCE_WEIGHT_TECHNICAL: float = float(os.getenv("CONFIDENCE_WEIGHT_TECHNICAL", "0.20"))
    CRITICAL_FAILURE_CONFIDENCE_CAP: float = float(os.getenv("CRITICAL_FAILURE_CONFIDENCE_CAP", "0.49"))

    # Generation Contract & Context Packing Flags (Grounded RAG)
    GROUNDED_CONTRACT_ENABLED: bool = os.getenv("GROUNDED_CONTRACT_ENABLED", "True").lower() in ("true", "1")
    GROUNDED_GENERATOR_MODEL: str = os.getenv("GROUNDED_GENERATOR_MODEL", "qwen/qwen3.8-27b")
    GROUNDED_TEMPERATURE: float = float(os.getenv("GROUNDED_TEMPERATURE", "0.15"))
    ANSWER_TEMPERATURE: float = float(os.getenv("ANSWER_TEMPERATURE", "0.10"))
    CONTEXT_PACKING_TOKEN_LIMIT: int = int(os.getenv("CONTEXT_PACKING_TOKEN_LIMIT", "3000"))
    CONTEXT_BASE_TOKEN_BUDGET: int = int(os.getenv("CONTEXT_BASE_TOKEN_BUDGET", "1500"))
    CONTEXT_PER_MODULE_TOKEN_BUDGET: int = int(os.getenv("CONTEXT_PER_MODULE_TOKEN_BUDGET", "600"))
    RETRIEVAL_CALIBRATED_THRESHOLD: float = float(os.getenv("RETRIEVAL_CALIBRATED_THRESHOLD", "0.6761"))
    DEDUPE_SIMILARITY_THRESHOLD: float = float(os.getenv("DEDUPE_SIMILARITY_THRESHOLD", "0.85"))
    PROMPT_PATH_GROUNDED_ANSWER: Path = (BASE_DIR / "app" / "prompts" / "grounded_answer.txt")

    # Tier Ranking Weights (relevance * tier_weight)
    TIER_WEIGHT_OFFICIAL_SAP: float = float(os.getenv("TIER_WEIGHT_OFFICIAL_SAP", "1.0"))
    TIER_WEIGHT_BOOK: float = float(os.getenv("TIER_WEIGHT_BOOK", "0.85"))
    TIER_WEIGHT_OFFICIAL_WEB: float = float(os.getenv("TIER_WEIGHT_OFFICIAL_WEB", "0.80"))
    TIER_WEIGHT_FORUM_WEB: float = float(os.getenv("TIER_WEIGHT_FORUM_WEB", "0.50"))
    TIER_WEIGHT_SELF_AUTHORED: float = float(os.getenv("TIER_WEIGHT_SELF_AUTHORED", "0.60"))
    ENABLE_SENTENCE_COMPRESSION: bool = os.getenv("ENABLE_SENTENCE_COMPRESSION", "False").lower() in ("true", "1")

    # Phase 1 & Advanced Architecture Feature Flags (Default OFF)
    SHADOW_MODE_ENABLED: bool = os.getenv("SHADOW_MODE_ENABLED", "False").lower() in ("true", "1")
    EXCLUDE_OFF_DOMAIN_DOCS: bool = os.getenv("EXCLUDE_OFF_DOMAIN_DOCS", "False").lower() in ("true", "1")
    USE_CORPUS_METADATA_V2: bool = os.getenv("USE_CORPUS_METADATA_V2", "False").lower() in ("true", "1")

    # GitHub Repository Retrieval & Multi-Source Comparison Feature Flags (Strictly Default FALSE)
    REPO_SOURCE_ENABLED: bool = os.getenv("REPO_SOURCE_ENABLED", "False").lower() in ("true", "1")
    MULTI_SOURCE_COMPARE_ENABLED: bool = os.getenv("MULTI_SOURCE_COMPARE_ENABLED", "False").lower() in ("true", "1")
    TIER_WEIGHT_GITHUB_REPO: float = float(os.getenv("TIER_WEIGHT_GITHUB_REPO", "0.80"))
    REPO_GATE_CALIBRATED_THRESHOLD: float = float(os.getenv("REPO_GATE_CALIBRATED_THRESHOLD", "0.65"))
    REPO_MIN_CHUNKS_THRESHOLD: int = int(os.getenv("REPO_MIN_CHUNKS_THRESHOLD", "10"))
    REPO_SNAPSHOTS_DIR: Path = BASE_DIR / "data" / "github_snapshots"

    # Extended Official SAP Web & Community Sources Feature Flags (Strictly Default FALSE)
    SAP_WEB_SOURCES_ENABLED: bool = os.getenv("SAP_WEB_SOURCES_ENABLED", "False").lower() in ("true", "1")
    TIER_WEIGHT_OFFICIAL_DEV_DOCS: float = float(os.getenv("TIER_WEIGHT_OFFICIAL_DEV_DOCS", "0.85"))
    TIER_WEIGHT_OFFICIAL_HELP_DOCS: float = float(os.getenv("TIER_WEIGHT_OFFICIAL_HELP_DOCS", "0.85"))
    TIER_WEIGHT_SAP_COMMUNITY: float = float(os.getenv("TIER_WEIGHT_SAP_COMMUNITY", "0.50"))
    WEB_DOC_SNAPSHOTS_DIR: Path = BASE_DIR / "data" / "web_doc_snapshots"

    # Rate Limiting & Backoff Settings
    RATE_LIMIT_MAX_RETRIES: int = int(os.getenv("RATE_LIMIT_MAX_RETRIES", "3"))
    RATE_LIMIT_BASE_BACKOFF_SEC: float = float(os.getenv("RATE_LIMIT_BASE_BACKOFF_SEC", "2.0"))

    # Web Fallback & Self-Hosted Search Providers (SearXNG + Siftdog)
    WEB_FALLBACK_ENABLED: bool = os.getenv("WEB_FALLBACK_ENABLED", "True").lower() in ("true", "1")
    WEB_SEARCH_API_KEY: str = os.getenv("WEB_SEARCH_API_KEY", "")
    SEARCH_PROVIDER: str = os.getenv("SEARCH_PROVIDER", "siftdog")  # "siftdog", "searxng", "tavily"
    SIFTDOG_URL: str = os.getenv("SIFTDOG_URL", "http://127.0.0.1:8088")
    SIFTDOG_API_KEY: str = os.getenv("SIFTDOG_API_KEY", "")
    SEARXNG_URL: str = os.getenv("SEARXNG_URL", "http://127.0.0.1:8089")
    SEARCH_TIMEOUT_SECONDS: float = float(os.getenv("SEARCH_TIMEOUT_SECONDS", "15.0"))
    SEARCH_MAX_RETRIES: int = int(os.getenv("SEARCH_MAX_RETRIES", "2"))
    SEARCH_FALLBACK_TO_SEARXNG: bool = os.getenv("SEARCH_FALLBACK_TO_SEARXNG", "True").lower() in ("true", "1")
    SEARCH_EXTRACTION_ENABLED: bool = os.getenv("SEARCH_EXTRACTION_ENABLED", "True").lower() in ("true", "1")
    SEARCH_DEFAULT_TOPIC: str = os.getenv("SEARCH_DEFAULT_TOPIC", "general")

    # Canonical knowledge-base source directory (at repo root if present).
    # Keep exactly one source location so ingestion results can be reconciled with
    # the on-disk inventory and an operator never has to guess which folder is live.
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

# Credentials that were committed to this repository, so anyone can read them.
PUBLISHED_SECRETS = frozenset({
    "sap-super-secret-jwt-key-2026-production-ready",
    "sap-admin-dev-secret-key-999",
    "Vamshi@06",
})
MIN_SECRET_LENGTH = 32
MIN_ADMIN_PASSWORD_LENGTH = 12


def security_settings_errors(s: Settings = settings) -> list:
    """Problems that make the configured secrets unsafe; the app refuses to start on any."""
    errors = []
    if len(s.JWT_SECRET) < MIN_SECRET_LENGTH or s.JWT_SECRET in PUBLISHED_SECRETS:
        errors.append(f"JWT_SECRET must be a private random value of at least {MIN_SECRET_LENGTH} characters.")
    if s.ADMIN_API_KEY and (len(s.ADMIN_API_KEY) < MIN_SECRET_LENGTH or s.ADMIN_API_KEY in PUBLISHED_SECRETS):
        errors.append(f"ADMIN_API_KEY must be empty or a private random value of at least {MIN_SECRET_LENGTH} characters.")
    if bool(s.SUPER_ADMIN_EMAIL.strip()) != bool(s.SUPER_ADMIN_PASSWORD):
        errors.append("Set both SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD, or neither.")
    elif s.SUPER_ADMIN_PASSWORD and (
        len(s.SUPER_ADMIN_PASSWORD) < MIN_ADMIN_PASSWORD_LENGTH or s.SUPER_ADMIN_PASSWORD in PUBLISHED_SECRETS
    ):
        errors.append(f"SUPER_ADMIN_PASSWORD must be a private password of at least {MIN_ADMIN_PASSWORD_LENGTH} characters.")
    return errors

