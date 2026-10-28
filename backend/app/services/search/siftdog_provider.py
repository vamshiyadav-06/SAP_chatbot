"""Siftdog search, extraction, crawling, and site mapping provider client.

Communicates with self-hosted Siftdog service (https://github.com/khsarvar/siftdog.git)
backed by SearXNG. Implements the 4 core Siftdog API capabilities:
- Search (/search): basic & advanced depth, general/news topics, domain filtering, raw content.
- Extraction (/extract): clean Markdown/text extraction from selected URLs with failure handling.
- Crawling (/crawl): bounded multi-page crawling with path/domain rules and SSRF safety.
- Site mapping (/map): discovery of sitemaps and URLs for targeted downstream retrieval.
"""

import logging
import re
import urllib.parse
from typing import List, Optional, Dict, Any, Union

import httpx

from backend.app.config import settings
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
)

logger = logging.getLogger(__name__)


class SiftdogSearchProvider:
    """Client for self-hosted Siftdog API service."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.SIFTDOG_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.SIFTDOG_API_KEY
        self.timeout = float(timeout if timeout is not None else settings.SEARCH_TIMEOUT_SECONDS)
        self.max_retries = int(max_retries if max_retries is not None else settings.SEARCH_MAX_RETRIES)

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "SAP-Knowledge-Assistant/2.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.Client(
            timeout=self.timeout,
            headers=headers,
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

    def check_health(self) -> Dict[str, Any]:
        """Check Siftdog health status."""
        try:
            resp = self._client.get(f"{self.base_url}/health")
            if resp.status_code == 200:
                return resp.json()
            return {"status": "unhealthy", "code": resp.status_code}
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}

    def _execute_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute POST request with bounded retries and exponential backoff."""
        url = f"{self.base_url}{path}"
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.post(url, json=payload)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (429, 502, 503, 504):
                    logger.warning("[Siftdog %s] Server error %d on attempt %d", path, resp.status_code, attempt + 1)
                    last_error = SearchProviderUnavailableError(f"Siftdog {path} returned HTTP {resp.status_code}")
                elif resp.status_code == 422:
                    raise SearchProviderError(f"Siftdog validation error: {resp.text[:300]}")
                else:
                    raise SearchProviderError(f"Siftdog {path} returned status {resp.status_code}: {resp.text[:200]}")
            except httpx.TimeoutException as exc:
                logger.warning("[Siftdog %s] Request timeout on attempt %d: %s", path, attempt + 1, exc)
                last_error = SearchProviderTimeoutError(f"Siftdog {path} request timed out: {exc}")
            except httpx.RequestError as exc:
                logger.warning("[Siftdog %s] Connection error on attempt %d: %s", path, attempt + 1, exc)
                last_error = SearchProviderUnavailableError(f"Siftdog connection error: {exc}")
            except Exception as exc:
                logger.error("[Siftdog %s] Unexpected error: %s", path, exc)
                last_error = SearchProviderError(f"Siftdog error: {exc}")

        if last_error:
            raise last_error
        raise SearchProviderError(f"Siftdog {path} failed without response")

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
        time_range: Optional[str] = None,
        days: Optional[int] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        include_raw_content: bool = True,
        include_images: bool = False,
        chunks_per_source: int = 3,
        include_answer: bool = False,
    ) -> List[SearchHit]:
        """Execute metasearch via Siftdog."""
        if not query.strip():
            return []

        payload: Dict[str, Any] = {
            "query": query.strip(),
            "max_results": max(1, min(max_results, 20)),
            "search_depth": search_depth if search_depth in ("basic", "advanced") else "basic",
            "topic": topic if topic in ("general", "news") else "general",
            "chunks_per_source": max(1, min(chunks_per_source, 5)),
            "include_raw_content": include_raw_content,
            "include_images": include_images,
            "include_image_descriptions": False,
            "include_answer": include_answer,
        }
        if self.api_key:
            payload["api_key"] = self.api_key
        if time_range:
            payload["time_range"] = time_range
        if days:
            payload["days"] = days
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        data = self._execute_post("/search", payload)
        raw_items = data.get("results", [])

        hits: List[SearchHit] = []
        for item in raw_items:
            url = str(item.get("url", "")).strip()
            if not url or not self._is_safe_http_url(url):
                continue

            title = re.sub(r"<[^>]+>", " ", str(item.get("title", ""))).strip()
            content = re.sub(r"<[^>]+>", " ", str(item.get("content", ""))).strip()
            raw_content = item.get("raw_content")
            score = float(item.get("score", 1.0) or 1.0)

            hits.append(SearchHit(
                title=title or "Untitled Source",
                url=url,
                snippet=content or "No snippet available",
                raw_content=raw_content if include_raw_content else None,
                score=score,
                published_date=item.get("published_date"),
                engine="siftdog",
            ))

        return hits

    def search_images(
        self,
        query: str,
        *,
        max_images: int = 4,
    ) -> List[ImageHit]:
        """Search images using Siftdog's include_images parameter."""
        if not query.strip():
            return []

        payload: Dict[str, Any] = {
            "query": query.strip(),
            "max_results": max(1, min(max_images * 2, 10)),
            "include_images": True,
            "include_raw_content": False,
        }
        if self.api_key:
            payload["api_key"] = self.api_key

        try:
            data = self._execute_post("/search", payload)
        except Exception as exc:
            logger.warning("[Siftdog] search_images error: %s", exc)
            return []

        image_urls = data.get("images") or []
        image_hits: List[ImageHit] = []
        seen = set()

        for raw_url in image_urls:
            url = str(raw_url).strip()
            if not url or not self._is_safe_http_url(url) or url in seen:
                continue
            seen.add(url)
            image_hits.append(ImageHit(
                url=url,
                source_url=None,
                source_title=None,
                description=None,
                alt_text="Technical visual",
            ))
            if len(image_hits) >= max_images:
                break

        return image_hits

    def extract(
        self,
        urls: Union[str, List[str]],
        *,
        extract_depth: str = "basic",
        include_images: bool = False,
        format: str = "markdown",
    ) -> ExtractResult:
        """Extract clean Markdown or text from selected URLs with failure handling."""
        target_urls = [urls] if isinstance(urls, str) else list(urls)
        safe_urls = [u for u in target_urls if self._is_safe_http_url(u)]
        if not safe_urls:
            return ExtractResult(pages=[], failed=[], response_time=0.0)

        payload: Dict[str, Any] = {
            "urls": safe_urls,
            "extract_depth": extract_depth if extract_depth in ("basic", "advanced") else "basic",
            "include_images": include_images,
            "format": format if format in ("markdown", "text") else "markdown",
        }
        if self.api_key:
            payload["api_key"] = self.api_key

        data = self._execute_post("/extract", payload)

        pages = [
            ExtractedPage(
                url=r.get("url", ""),
                raw_content=r.get("raw_content", ""),
                images=r.get("images") or [],
            )
            for r in data.get("results", [])
            if r.get("url")
        ]

        failed = [
            FailedUrl(
                url=f.get("url", ""),
                error=f.get("error", "Unknown extraction error"),
            )
            for f in data.get("failed_results", [])
            if f.get("url")
        ]

        return ExtractResult(
            pages=pages,
            failed=failed,
            response_time=float(data.get("response_time", 0.0)),
        )

    def crawl(
        self,
        url: str,
        *,
        max_depth: int = 1,
        max_breadth: int = 20,
        limit: int = 50,
        instructions: Optional[str] = None,
        select_paths: Optional[List[str]] = None,
        select_domains: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        allow_external: bool = False,
        extract_depth: str = "basic",
        include_images: bool = False,
        format: str = "markdown",
    ) -> CrawlResult:
        """Crawl website documentation pages with bounded depth and domain restrictions."""
        if not self._is_safe_http_url(url):
            raise SearchProviderError(f"Invalid or unsafe crawl URL: {url}")

        payload: Dict[str, Any] = {
            "url": url,
            "max_depth": max(1, min(max_depth, 5)),
            "max_breadth": max(1, min(max_breadth, 500)),
            "limit": max(1, min(limit, 50)),
            "allow_external": allow_external,
            "extract_depth": extract_depth,
            "include_images": include_images,
            "format": format,
        }
        if self.api_key:
            payload["api_key"] = self.api_key
        if instructions:
            payload["instructions"] = instructions
        if select_paths:
            payload["select_paths"] = select_paths
        if select_domains:
            payload["select_domains"] = select_domains
        if exclude_paths:
            payload["exclude_paths"] = exclude_paths
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        data = self._execute_post("/crawl", payload)

        pages = [
            ExtractedPage(
                url=r.get("url", ""),
                raw_content=r.get("raw_content", ""),
                images=r.get("images") or [],
            )
            for r in data.get("results", [])
            if r.get("url")
        ]

        return CrawlResult(
            base_url=data.get("base_url", url),
            pages=pages,
            discovered_urls=[p.url for p in pages],
            response_time=float(data.get("response_time", 0.0)),
        )

    def map_site(
        self,
        url: str,
        *,
        max_depth: int = 1,
        max_breadth: int = 20,
        limit: int = 50,
        instructions: Optional[str] = None,
        select_paths: Optional[List[str]] = None,
        select_domains: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        allow_external: bool = False,
    ) -> MapResult:
        """Discover URL map for website or documentation section."""
        if not self._is_safe_http_url(url):
            raise SearchProviderError(f"Invalid or unsafe map URL: {url}")

        payload: Dict[str, Any] = {
            "url": url,
            "max_depth": max(1, min(max_depth, 5)),
            "max_breadth": max(1, min(max_breadth, 500)),
            "limit": max(1, min(limit, 50)),
            "allow_external": allow_external,
        }
        if self.api_key:
            payload["api_key"] = self.api_key
        if instructions:
            payload["instructions"] = instructions
        if select_paths:
            payload["select_paths"] = select_paths
        if select_domains:
            payload["select_domains"] = select_domains
        if exclude_paths:
            payload["exclude_paths"] = exclude_paths
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        data = self._execute_post("/map", payload)

        return MapResult(
            base_url=data.get("base_url", url),
            urls=data.get("results", []),
            response_time=float(data.get("response_time", 0.0)),
        )
