"""SearXNG metasearch provider client.

Communicates with self-hosted SearXNG instance over HTTP JSON API.
Supports general web, news, technical documentation, and visual image search with
categories, engines, time-range, pagination, safe-search, and domain filtering.
"""

import logging
import re
import urllib.parse
from typing import List, Optional, Dict, Any

import httpx

from backend.app.config import settings
from backend.app.services.search.base import (
    SearchHit,
    ImageHit,
    SearchProviderError,
    SearchProviderUnavailableError,
    SearchProviderTimeoutError,
)

logger = logging.getLogger(__name__)


class SearxngSearchProvider:
    """Client for self-hosted SearXNG metasearch engine."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.SEARXNG_URL).rstrip("/")
        self.timeout = float(timeout if timeout is not None else settings.SEARCH_TIMEOUT_SECONDS)
        self.max_retries = int(max_retries if max_retries is not None else settings.SEARCH_MAX_RETRIES)
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={"User-Agent": "SAP-Knowledge-Assistant/2.0"},
            follow_redirects=True,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def _is_safe_http_url(url: Any) -> bool:
        """Validate that URL is absolute HTTP/HTTPS."""
        try:
            val = str(url or "").strip()
            parts = urllib.parse.urlsplit(val)
            return parts.scheme.lower() in ("http", "https") and bool(parts.netloc)
        except Exception:
            return False

    @staticmethod
    def _matches_domains(url: str, domains: List[str]) -> bool:
        """Check if URL host matches any domain in list."""
        try:
            host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
        except Exception:
            return False
        return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)

    def _execute_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute GET request with bounded retries and exponential backoff."""
        url = f"{self.base_url}/search"
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.get(url, params=params)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (429, 502, 503, 504):
                    logger.warning("[SearXNG] Upstream error %d on attempt %d: %s", resp.status_code, attempt + 1, resp.text[:200])
                    last_error = SearchProviderUnavailableError(f"SearXNG returned HTTP {resp.status_code}")
                else:
                    raise SearchProviderError(f"SearXNG returned status {resp.status_code}: {resp.text[:200]}")
            except httpx.TimeoutException as exc:
                logger.warning("[SearXNG] Request timeout on attempt %d: %s", attempt + 1, exc)
                last_error = SearchProviderTimeoutError(f"SearXNG request timed out: {exc}")
            except httpx.RequestError as exc:
                logger.warning("[SearXNG] Connection error on attempt %d: %s", attempt + 1, exc)
                last_error = SearchProviderUnavailableError(f"SearXNG connection error: {exc}")
            except Exception as exc:
                logger.error("[SearXNG] Unexpected error: %s", exc)
                last_error = SearchProviderError(f"SearXNG error: {exc}")

        if last_error:
            raise last_error
        raise SearchProviderError("SearXNG search failed without response")

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
        time_range: Optional[str] = None,
        language: str = "en",
        safesearch: int = 0,
        pageno: int = 1,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        include_raw_content: bool = True,
        include_images: bool = False,
        categories: Optional[str] = None,
        engines: Optional[str] = None,
    ) -> List[SearchHit]:
        """Execute web or news search via SearXNG."""
        if not query.strip():
            return []

        # Determine category
        cat = categories
        if not cat:
            cat = "news" if topic == "news" else "general"

        params: Dict[str, Any] = {
            "q": query.strip(),
            "format": "json",
            "categories": cat,
            "safesearch": safesearch,
            "pageno": pageno,
        }
        if language:
            params["language"] = language
        if time_range:
            params["time_range"] = time_range
        if engines:
            params["engines"] = engines

        data = self._execute_request(params)
        raw_items = data.get("results", [])

        hits: List[SearchHit] = []
        seen_urls = set()

        for item in raw_items:
            url = str(item.get("url", "")).strip()
            if not url or not self._is_safe_http_url(url) or url in seen_urls:
                continue

            if include_domains and not self._matches_domains(url, include_domains):
                continue
            if exclude_domains and self._matches_domains(url, exclude_domains):
                continue

            seen_urls.add(url)
            title = re.sub(r"<[^>]+>", " ", str(item.get("title", ""))).strip()
            content = re.sub(r"<[^>]+>", " ", str(item.get("content", ""))).strip()
            score = float(item.get("score", 1.0) or 1.0)

            hits.append(SearchHit(
                title=title or "Untitled Web Source",
                url=url,
                snippet=content or "No snippet available",
                raw_content=content if include_raw_content else None,
                score=score,
                published_date=item.get("publishedDate") or item.get("pubdate"),
                engine=item.get("engine"),
            ))

            if len(hits) >= max_results:
                break

        return hits

    def search_images(
        self,
        query: str,
        *,
        max_images: int = 4,
        safesearch: int = 0,
        pageno: int = 1,
        include_domains: Optional[List[str]] = None,
    ) -> List[ImageHit]:
        """Search image category on SearXNG across configured visual engines."""
        if not query.strip():
            return []

        params: Dict[str, Any] = {
            "q": query.strip(),
            "format": "json",
            "categories": "images",
            "safesearch": safesearch,
            "pageno": pageno,
        }

        try:
            data = self._execute_request(params)
        except Exception as exc:
            logger.warning("[SearXNG] Image search query '%s' failed: %s", query[:50], exc)
            return []

        raw_items = data.get("results", [])
        image_hits: List[ImageHit] = []
        seen_urls = set()

        for item in raw_items:
            img_url = item.get("img_src") or item.get("thumbnail_src") or item.get("url")
            if not img_url or not self._is_safe_http_url(img_url) or img_url in seen_urls:
                continue

            source_url = item.get("url")
            if include_domains and source_url:
                if not self._matches_domains(source_url, include_domains):
                    continue

            seen_urls.add(img_url)
            title = re.sub(r"<[^>]+>", " ", str(item.get("title", ""))).strip()
            content = re.sub(r"<[^>]+>", " ", str(item.get("content", ""))).strip()
            thumb = item.get("thumbnail_src") or item.get("thumbnail")

            image_hits.append(ImageHit(
                url=img_url,
                source_url=source_url if self._is_safe_http_url(source_url) else None,
                source_title=title or None,
                description=content or title or None,
                alt_text=title or content or "Technical visual",
                thumbnail_url=thumb if self._is_safe_http_url(thumb) else None,
                resolution=item.get("resolution"),
                img_format=item.get("img_format"),
            ))

            if len(image_hits) >= max_images:
                break

        return image_hits
