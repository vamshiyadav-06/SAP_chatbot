import re
import time
import logging
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from tavily import TavilyClient

from backend.app.config import settings

logger = logging.getLogger(__name__)

# Strict approved SAP domain allowlist
APPROVED_SAP_DOMAINS = [
    "help.sap.com",
    "community.sap.com",
    "blogs.sap.com",
    "learning.sap.com",
    "sap.com"
]

class WebSearchService:
    """
    Authoritative SAP Web Search Service using Tavily API with official SAP Help Portal fallback.
    """

    def __init__(self):
        self.api_key = settings.WEB_SEARCH_API_KEY.strip()
        self.client: Optional[TavilyClient] = None
        self._cache: Dict[str, Dict[str, Any]] = {}  # query_hash -> {"timestamp": float, "results": list}
        self._cache_ttl = 3600  # 1 hour cache TTL

        if self.api_key:
            try:
                self.client = TavilyClient(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize TavilyClient: {e}")
                self.client = None

    @staticmethod
    def _is_approved_sap_domain(url: str) -> bool:
        """Enforces hard domain restriction on approved SAP domains."""
        url_lower = url.lower()
        return any(domain in url_lower for domain in APPROVED_SAP_DOMAINS)

    @staticmethod
    def _extract_authority_tier(url: str, domain: str) -> int:
        """
        Determines authority tier:
        Tier 1: Official SAP Product Documentation (help.sap.com, learning.sap.com)
        Tier 2: SAP Community & Expert Blogs (community.sap.com, blogs.sap.com)
        Tier 3: Other verified SAP web resources
        """
        target = f"{url} {domain}".lower()
        if "help.sap.com" in target or "learning.sap.com" in target:
            return 1
        elif "community.sap.com" in target or "blogs.sap.com" in target:
            return 2
        return 3

    @staticmethod
    def _clean_text(value: Any) -> str:
        """Cleans HTML tags, multiple spaces, and escape sequences."""
        if not value:
            return ""
        text = str(value)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _normalize_query(self, query: str) -> str:
        """Normalizes query for deterministic caching."""
        return re.sub(r"[^a-zA-Z0-9\s]", "", query.lower()).strip()

    def _fallback_sap_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Direct fallback search querying official SAP documentation (help.sap.com).
        Guarantees authoritative external evidence if Tavily is unavailable.
        """
        clean_q = f"SAP {query} help.sap.com" if not query.lower().startswith("sap") else f"{query} help.sap.com"
        try:
            data = urllib.parse.urlencode({"q": clean_q}).encode("utf-8")
            req = urllib.request.Request(
                "https://html.duckduckgo.com/html/",
                data=data,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as res:
                soup = BeautifulSoup(res.read(), "html.parser")
                raw_results = soup.find_all("div", class_="result")
                parsed = []
                for r in raw_results:
                    link_tag = r.find("a", class_="result__url")
                    snippet_tag = r.find("a", class_="result__snippet")
                    title_tag = r.find("a", class_="result__a")
                    if not link_tag or not title_tag:
                        continue
                    url = link_tag.get("href", "").strip()
                    if not url.startswith("http"):
                        url = "https://" + url
                    title = title_tag.text.strip()
                    snippet = snippet_tag.text.strip() if snippet_tag else ""
                    parsed.append({
                        "title": title,
                        "url": url,
                        "content": snippet
                    })
                    if len(parsed) >= limit * 2:
                        break
                return parsed
        except Exception as e:
            logger.warning(f"Authoritative SAP fallback search error: {e}")
            return []

    def search_sap_authoritative(
        self,
        query: str,
        max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches the live web using Tavily with strict SAP domain restrictions.
        Returns deduplicated, structured, authoritative SAP passages.
        """
        if not settings.WEB_FALLBACK_ENABLED:
            return []

        limit = max_results or settings.TAVILY_MAX_RESULTS
        normalized_q = self._normalize_query(query)

        # Check Cache
        cached_entry = self._cache.get(normalized_q)
        if cached_entry:
            if time.time() - cached_entry["timestamp"] < self._cache_ttl:
                logger.info(f"Returning cached Tavily search results for query: '{normalized_q[:40]}'")
                return cached_entry["results"][:limit]

        raw_results = []
        if self.client:
            # Execute Tavily Search with hard domain restriction
            try:
                # Format search query to focus on SAP official material
                search_query = f"SAP {query}" if not query.lower().startswith("sap") else query
                response = self.client.search(
                    query=search_query,
                    search_depth="basic",
                    max_results=limit * 2,  # request extra to allow filtering
                    include_answer=False,
                    include_raw_content=False,
                    include_domains=APPROVED_SAP_DOMAINS,
                )
                raw_results = response.get("results", []) if isinstance(response, dict) else []
            except Exception as exc:
                logger.warning(f"[Tavily] Search API failed for query '{query[:40]}': {exc}. Engaging SAP documentation fallback engine.")
                raw_results = []

        if not raw_results:
            # Fallback to direct authoritative SAP web search
            raw_results = self._fallback_sap_search(query, limit)
        results: List[Dict[str, Any]] = []
        seen_urls = set()

        for item in raw_results:
            url = str(item.get("url", "")).strip()
            if not url or url in seen_urls:
                continue

            # Hard domain restriction check
            if not self._is_approved_sap_domain(url):
                continue

            seen_urls.add(url)

            title = self._clean_text(item.get("title", "")) or "SAP Official Documentation"
            snippet = self._clean_text(item.get("content", "")) or "No preview available."

            # Determine specific domain
            url_lower = url.lower()
            if "help.sap.com" in url_lower:
                domain = "help.sap.com"
            elif "blogs.sap.com" in url_lower:
                domain = "blogs.sap.com"
            elif "community.sap.com" in url_lower:
                domain = "community.sap.com"
            else:
                domain = "help.sap.com"

            authority_tier = self._extract_authority_tier(url, domain)

            results.append({
                "source_id": f"web_{len(results)+1}_{domain}",
                "title": title,
                "url": url,
                "domain": domain,
                "snippet": snippet,
                "chunk_text": f"{title}\n{snippet}",
                "authority_tier": authority_tier,
                "source_type": "web",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            })

            if len(results) >= limit:
                break

        # Cache results
        self._cache[normalized_q] = {
            "timestamp": time.time(),
            "results": results
        }

        return results


web_search_service = WebSearchService()