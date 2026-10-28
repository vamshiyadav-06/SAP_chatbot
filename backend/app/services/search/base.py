"""Base types and exceptions for unified web search, extraction, crawling, and image discovery."""

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Dict, Any


class SearchProviderError(Exception):
    """Base exception for search provider errors."""
    pass


class SearchProviderUnavailableError(SearchProviderError):
    """Raised when an external search engine or service is down or unreachable."""
    pass


class SearchProviderTimeoutError(SearchProviderError):
    """Raised when an external search request times out."""
    pass


@dataclass
class SearchHit:
    """Normalized search result hit."""
    title: str
    url: str
    snippet: str
    raw_content: Optional[str] = None
    score: float = 0.0
    published_date: Optional[str] = None
    engine: Optional[str] = None


@dataclass
class ImageHit:
    """Normalized visual search hit."""
    url: str
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    description: Optional[str] = None
    alt_text: Optional[str] = None
    thumbnail_url: Optional[str] = None
    resolution: Optional[str] = None
    img_format: Optional[str] = None


@dataclass
class ExtractedPage:
    """Normalized extracted web page content."""
    url: str
    raw_content: str
    title: Optional[str] = None
    images: List[str] = field(default_factory=list)
    published_date: Optional[str] = None


@dataclass
class FailedUrl:
    """Record of a URL that failed extraction."""
    url: str
    error: str


@dataclass
class ExtractResult:
    """Batch extraction outcome."""
    pages: List[ExtractedPage] = field(default_factory=list)
    failed: List[FailedUrl] = field(default_factory=list)
    response_time: float = 0.0


@dataclass
class CrawlResult:
    """Result of a site crawling operation."""
    base_url: str
    pages: List[ExtractedPage] = field(default_factory=list)
    discovered_urls: List[str] = field(default_factory=list)
    response_time: float = 0.0


@dataclass
class MapResult:
    """Result of a site mapping operation."""
    base_url: str
    urls: List[str] = field(default_factory=list)
    response_time: float = 0.0


class SearchProviderInterface(Protocol):
    """Interface defining capabilities of search backends."""

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
        time_range: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        include_raw_content: bool = True,
        include_images: bool = False,
    ) -> List[SearchHit]:
        ...

    def search_images(
        self,
        query: str,
        *,
        max_images: int = 4,
    ) -> List[ImageHit]:
        ...
