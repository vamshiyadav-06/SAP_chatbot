"""Search package exporting unified search and provider implementations."""

from backend.app.services.search.base import (
    SearchHit,
    ImageHit,
    ExtractedPage,
    FailedUrl,
    ExtractResult,
    CrawlResult,
    MapResult,
    SearchProviderError,
    SearchProviderUnavailableError,
    SearchProviderTimeoutError,
    SearchProviderInterface,
)
from backend.app.services.search.searxng_provider import SearxngSearchProvider
from backend.app.services.search.siftdog_provider import SiftdogSearchProvider
from backend.app.services.search.tavily_provider import TavilySearchProvider
from backend.app.services.search.unified_service import (
    UnifiedSearchService,
    unified_search_service,
    APPROVED_SAP_DOMAINS,
)

__all__ = [
    "SearchHit",
    "ImageHit",
    "ExtractedPage",
    "FailedUrl",
    "ExtractResult",
    "CrawlResult",
    "MapResult",
    "SearchProviderError",
    "SearchProviderUnavailableError",
    "SearchProviderTimeoutError",
    "SearchProviderInterface",
    "SearxngSearchProvider",
    "SiftdogSearchProvider",
    "TavilySearchProvider",
    "UnifiedSearchService",
    "unified_search_service",
    "APPROVED_SAP_DOMAINS",
]
