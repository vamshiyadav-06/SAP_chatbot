"""Unified Search Service orchestrator.

Routes queries across Siftdog, SearXNG, and Tavily with intelligent failover,
authoritative SAP domain prioritization, content extraction, and dedicated image search.
"""

import logging
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Union

from backend.app.config import settings
from backend.app.services.search.base import (
    SearchHit,
    ImageHit,
    ExtractedPage,
    ExtractResult,
    CrawlResult,
    MapResult,
    SearchProviderError,
    SearchProviderUnavailableError,
)
from backend.app.services.search.searxng_provider import SearxngSearchProvider
from backend.app.services.search.siftdog_provider import SiftdogSearchProvider
from backend.app.services.search.tavily_provider import TavilySearchProvider

logger = logging.getLogger(__name__)

# Strict approved SAP domain allowlist
APPROVED_SAP_DOMAINS = [
    "help.sap.com",
    "community.sap.com",
    "blogs.sap.com",
    "learning.sap.com",
    "sap.com",
]


class UnifiedSearchService:
    """High-level search service managing self-hosted and cloud providers."""

    def __init__(self):
        self.searxng = SearxngSearchProvider()
        self.siftdog = SiftdogSearchProvider()
        self.tavily = TavilySearchProvider()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 3600  # 1 hour TTL

    @staticmethod
    def _hostname(url: str) -> str:
        try:
            host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
        except Exception:
            return ""
        return host[4:] if host.startswith("www.") else host

    @staticmethod
    def is_approved_sap_domain(url: str) -> bool:
        """Enforces hard domain restriction on approved SAP domains."""
        try:
            hostname = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
        except Exception:
            return False
        return any(hostname == domain or hostname.endswith("." + domain) for domain in APPROVED_SAP_DOMAINS)

    @staticmethod
    def classify_authority(url: str) -> str:
        """Classify source authority by hostname. Community content is distinct from official docs."""
        host = UnifiedSearchService._hostname(url)
        if host == "help.sap.com" or host.endswith(".help.sap.com"):
            return "official_sap_help"
        if host in ("me.sap.com", "launchpad.support.sap.com", "userapps.support.sap.com", "support.sap.com") \
                or host.endswith(".support.sap.com"):
            return "sap_support_note"
        if host == "learning.sap.com":
            return "sap_learning"
        if host in ("community.sap.com", "blogs.sap.com") or host.endswith(".community.sap.com"):
            return "sap_community"
        if host == "sap.com" or host.endswith(".sap.com"):
            return "official_sap_other"
        return "third_party"

    @staticmethod
    def extract_authority_tier(url: str, domain: str) -> int:
        """
        Determines authority tier:
        Tier 1: Official SAP Help Portal & Support Notes (help.sap.com, me.sap.com)
        Tier 2: SAP Community & Expert Blogs (community.sap.com, blogs.sap.com)
        Tier 3: Other verified SAP web resources
        """
        target = f"{url} {domain}".lower()
        if "help.sap.com" in target or "learning.sap.com" in target:
            return 1
        if UnifiedSearchService.classify_authority(url) == "sap_support_note":
            return 1
        elif "community.sap.com" in target or "blogs.sap.com" in target:
            return 2
        return 3

    @staticmethod
    def extract_release(text: str) -> Optional[str]:
        """Extract explicit SAP release stated in the text."""
        m = re.search(
            r"\bS/4\s?HANA(?:\s+Cloud(?:,?\s+(?:public|private)\s+edition)?)?(?:\s+on-premise)?(?:\s+edition)?\s*,?\s*"
            r"((?:19|20)\d{2}(?:\s+FPS\d{2})?)\b",
            text or "",
            re.IGNORECASE,
        )
        if m:
            return f"SAP S/4HANA {m.group(1)}"
        if re.search(r"\bECC\s*6\.0\b|\bSAP\s+ERP\s+6\.0\b", text or "", re.IGNORECASE):
            return "SAP ECC 6.0"
        if re.search(r"\bS/4\s?HANA\b", text or "", re.IGNORECASE):
            return "SAP S/4HANA (release not stated)"
        return None

    @staticmethod
    def wants_visuals(query: str) -> bool:
        """Return true only when the user has explicitly asked for visual material."""
        return bool(re.search(
            r"\b(image|images|diagram|architecture\s+diagram|visual|illustration|"
            r"screenshot|screen\s*shot|process\s*flow|flowchart|workflow\s+diagram)\b",
            query or "",
            flags=re.IGNORECASE,
        ))

    @staticmethod
    def technical_identifiers(query: str) -> List[str]:
        from backend.app.services.sap_identifier_validator import extract_identifiers
        return [i.value for i in extract_identifiers(query or "") if i.id_type != "sap_note"][:4]

    def build_search_query(self, query: str) -> str:
        """Exact technical identifiers (quoted) plus business context."""
        base = query if query.lower().startswith("sap") else f"SAP {query}"
        identifiers = [i for i in self.technical_identifiers(query) if f'"{i}"' not in base]
        if identifiers:
            base = f"{base} " + " ".join(f'"{i}"' for i in identifiers)
        return base[:400]

    @staticmethod
    def extract_relevant_passages(raw_content: str, query: str, max_chars: int = 1800) -> str:
        """Pick page paragraphs mentioning query identifiers and terms."""
        text = re.sub(r"[ \t]+", " ", str(raw_content or ""))
        if not text.strip():
            return ""
        identifiers = [i.lower() for i in UnifiedSearchService.technical_identifiers(query)]
        stop = {
            "what", "where", "when", "which", "with", "from", "that", "this", "have", "does", "can", "how",
            "the", "and", "for", "are", "sap", "manually", "view", "remove",
        }
        terms = {t for t in re.findall(r"[a-z0-9_/-]{3,}", (query or "").lower()) if t not in stop}
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[#*\-\d])", text) if len(p.strip()) >= 40]
        scored = []
        for idx, para in enumerate(paragraphs):
            low = para.lower()
            score = sum(3 for i in identifiers if i in low) + sum(1 for t in terms if t in low)
            if score:
                scored.append((score, idx, para))
        chosen, used = [], 0
        for score, idx, para in sorted(scored, key=lambda row: (-row[0], row[1])):
            if used >= max_chars:
                break
            piece = para[: max_chars - used]
            chosen.append((idx, piece))
            used += len(piece) + 2
        return "\n\n".join(p for _, p in sorted(chosen))

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
        provider: Optional[str] = None,
    ) -> List[SearchHit]:
        """Search using the active provider with automatic fallback."""
        active_provider = (provider or settings.SEARCH_PROVIDER or "siftdog").lower()

        # Strategy 1: Siftdog (Self-hosted search & extraction API)
        if active_provider == "siftdog":
            try:
                hits = self.siftdog.search(
                    query=query,
                    max_results=max_results,
                    search_depth=search_depth,
                    topic=topic,
                    time_range=time_range,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    include_raw_content=include_raw_content,
                )
                if hits:
                    return hits
            except Exception as exc:
                logger.warning("[UnifiedSearch] Siftdog search failed: %s. Falling back to SearXNG.", exc)

            # Fallback to direct SearXNG if enabled
            if settings.SEARCH_FALLBACK_TO_SEARXNG:
                try:
                    hits = self.searxng.search(
                        query=query,
                        max_results=max_results,
                        topic=topic,
                        time_range=time_range,
                        include_domains=include_domains,
                        exclude_domains=exclude_domains,
                        include_raw_content=include_raw_content,
                    )
                    if hits:
                        return hits
                except Exception as exc:
                    logger.warning("[UnifiedSearch] SearXNG fallback failed: %s.", exc)

        # Strategy 2: Direct SearXNG
        elif active_provider == "searxng":
            try:
                hits = self.searxng.search(
                    query=query,
                    max_results=max_results,
                    topic=topic,
                    time_range=time_range,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    include_raw_content=include_raw_content,
                )
                if hits:
                    return hits
            except Exception as exc:
                logger.warning("[UnifiedSearch] SearXNG search failed: %s.", exc)

        # Strategy 3: Tavily (cloud fallback)
        if self.tavily.is_available:
            try:
                return self.tavily.search(
                    query=query,
                    max_results=max_results,
                    search_depth=search_depth,
                    topic=topic,
                    time_range=time_range,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    include_raw_content=include_raw_content,
                )
            except Exception as exc:
                logger.warning("[UnifiedSearch] Tavily fallback search failed: %s.", exc)

        return []

    def search_images(
        self,
        query: str,
        *,
        max_images: int = 4,
        include_domains: Optional[List[str]] = None,
    ) -> List[ImageHit]:
        """Search images using SearXNG's multi-engine image discovery with Siftdog/Tavily fallback."""
        if not query.strip():
            return []

        # 1. Try SearXNG image search first (richest metadata: format, resolution, thumbnail)
        try:
            hits = self.searxng.search_images(
                query=query,
                max_images=max_images,
                include_domains=include_domains,
            )
            if hits:
                return hits
        except Exception as exc:
            logger.warning("[UnifiedSearch] SearXNG image search failed: %s", exc)

        # 2. Try Siftdog image search fallback
        try:
            hits = self.siftdog.search_images(query=query, max_images=max_images)
            if hits:
                return hits
        except Exception as exc:
            logger.warning("[UnifiedSearch] Siftdog image search failed: %s", exc)

        # 3. Try Tavily image search fallback
        if self.tavily.is_available:
            try:
                return self.tavily.search_images(query=query, max_images=max_images)
            except Exception as exc:
                logger.warning("[UnifiedSearch] Tavily image search fallback failed: %s", exc)

        return []

    def extract(
        self,
        urls: Union[str, List[str]],
        *,
        format: str = "markdown",
    ) -> ExtractResult:
        """Extract clean content from URLs using Siftdog."""
        return self.siftdog.extract(urls=urls, format=format)

    def crawl_site(
        self,
        url: str,
        *,
        max_depth: int = 1,
        max_breadth: int = 20,
        limit: int = 50,
        select_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
    ) -> CrawlResult:
        """Crawl website documentation using Siftdog."""
        return self.siftdog.crawl(
            url=url,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
            select_paths=select_paths,
            exclude_paths=exclude_paths,
        )

    def map_site(
        self,
        url: str,
        *,
        max_depth: int = 1,
        max_breadth: int = 20,
        limit: int = 50,
        select_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
    ) -> MapResult:
        """Map website structure using Siftdog."""
        return self.siftdog.map_site(
            url=url,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
            select_paths=select_paths,
            exclude_paths=exclude_paths,
        )


unified_search_service = UnifiedSearchService()
