"""Unit tests for SearXNG, Siftdog, and Unified Search Provider integrations."""

import json
from unittest.mock import MagicMock, patch
import pytest
import httpx

from backend.app.services.search.base import (
    SearchHit,
    ImageHit,
    ExtractedPage,
    FailedUrl,
    SearchProviderError,
    SearchProviderUnavailableError,
    SearchProviderTimeoutError,
)
from backend.app.services.search.searxng_provider import SearxngSearchProvider
from backend.app.services.search.siftdog_provider import SiftdogSearchProvider
from backend.app.services.search.unified_service import (
    UnifiedSearchService,
    APPROVED_SAP_DOMAINS,
)
from backend.app.services.web_search_service import WebSearchService


# ---------------------------------------------------------------------------
# SearXNG Provider Tests
# ---------------------------------------------------------------------------

def test_searxng_search_normalization_and_domain_filtering():
    provider = SearxngSearchProvider(base_url="http://test-searxng:8080")
    fake_json = {
        "results": [
            {
                "title": "SAP BRIM Overview",
                "url": "https://help.sap.com/docs/brim-overview",
                "content": "Billing and revenue innovation management overview...",
                "score": 2.5,
                "publishedDate": "2024-01-15",
                "engine": "google",
            },
            {
                "title": "External Forum",
                "url": "https://random-blog.com/sap",
                "content": "Random post",
                "score": 1.0,
            },
            {
                "title": "Invalid Scheme",
                "url": "javascript:alert(1)",
                "content": "malicious",
            },
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_json
    provider._client.get = MagicMock(return_value=mock_resp)

    hits = provider.search(
        "SAP BRIM",
        max_results=5,
        include_domains=["help.sap.com"],
        include_raw_content=True,
    )

    assert len(hits) == 1
    hit = hits[0]
    assert hit.title == "SAP BRIM Overview"
    assert hit.url == "https://help.sap.com/docs/brim-overview"
    assert hit.engine == "google"
    assert hit.score == 2.5
    assert hit.raw_content == "Billing and revenue innovation management overview..."

    # Check query params sent to SearXNG
    called_params = provider._client.get.call_args.kwargs["params"]
    assert called_params["q"] == "SAP BRIM"
    assert called_params["format"] == "json"
    assert called_params["categories"] == "general"


def test_searxng_image_search_normalization():
    provider = SearxngSearchProvider(base_url="http://test-searxng:8080")
    fake_json = {
        "results": [
            {
                "title": "SAP BRIM Architecture Diagram",
                "url": "https://help.sap.com/docs/architecture",
                "img_src": "https://help.sap.com/img/brim_arch.png",
                "thumbnail_src": "https://thumb.example.com/arch.png",
                "resolution": "1920x1080",
                "img_format": "PNG",
                "content": "Architecture flow diagram",
            },
            {
                "title": "Duplicate Image",
                "url": "https://other.com",
                "img_src": "https://help.sap.com/img/brim_arch.png",
            },
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_json
    provider._client.get = MagicMock(return_value=mock_resp)

    images = provider.search_images("SAP BRIM architecture", max_images=4)
    assert len(images) == 1
    img = images[0]
    assert img.url == "https://help.sap.com/img/brim_arch.png"
    assert img.thumbnail_url == "https://thumb.example.com/arch.png"
    assert img.source_url == "https://help.sap.com/docs/architecture"
    assert img.resolution == "1920x1080"
    assert img.img_format == "PNG"


def test_searxng_timeout_and_error_handling():
    provider = SearxngSearchProvider(base_url="http://test-searxng:8080", max_retries=1)
    provider._client.get = MagicMock(side_effect=httpx.TimeoutException("Read timed out"))

    with pytest.raises(SearchProviderTimeoutError):
        provider.search("SAP FI-CA")


# ---------------------------------------------------------------------------
# Siftdog Provider Tests
# ---------------------------------------------------------------------------

def test_siftdog_search_request_and_response():
    provider = SiftdogSearchProvider(base_url="http://test-siftdog:8088", api_key="secret-key")
    fake_json = {
        "query": "SAP Convergent Invoicing",
        "results": [
            {
                "title": "Convergent Invoicing",
                "url": "https://help.sap.com/ci",
                "content": "Billing process in CI",
                "raw_content": "# CI Documentation\nFull details here...",
                "score": 0.95,
                "published_date": "2024-02-01",
            }
        ],
        "response_time": 0.42,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_json
    provider._client.post = MagicMock(return_value=mock_resp)

    hits = provider.search(
        "SAP Convergent Invoicing",
        max_results=3,
        search_depth="advanced",
        include_raw_content=True,
    )

    assert len(hits) == 1
    assert hits[0].title == "Convergent Invoicing"
    assert hits[0].raw_content.startswith("# CI Documentation")

    sent_payload = provider._client.post.call_args.kwargs["json"]
    assert sent_payload["query"] == "SAP Convergent Invoicing"
    assert sent_payload["search_depth"] == "advanced"
    assert sent_payload["api_key"] == "secret-key"


def test_siftdog_extract_capabilities():
    provider = SiftdogSearchProvider(base_url="http://test-siftdog:8088")
    fake_json = {
        "results": [
            {
                "url": "https://help.sap.com/doc1",
                "raw_content": "Extracted Markdown content",
                "images": ["https://help.sap.com/img1.png"],
            }
        ],
        "failed_results": [
            {
                "url": "https://unreachable.com/doc2",
                "error": "Connection timed out",
            }
        ],
        "response_time": 0.85,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_json
    provider._client.post = MagicMock(return_value=mock_resp)

    res = provider.extract(["https://help.sap.com/doc1", "https://unreachable.com/doc2"])
    assert len(res.pages) == 1
    assert res.pages[0].url == "https://help.sap.com/doc1"
    assert res.pages[0].raw_content == "Extracted Markdown content"
    assert len(res.failed) == 1
    assert res.failed[0].url == "https://unreachable.com/doc2"


def test_siftdog_crawl_and_map():
    provider = SiftdogSearchProvider(base_url="http://test-siftdog:8088")

    # Crawl test
    crawl_resp = MagicMock()
    crawl_resp.status_code = 200
    crawl_resp.json.return_value = {
        "base_url": "https://help.sap.com/brim",
        "results": [
            {"url": "https://help.sap.com/brim/p1", "raw_content": "Page 1", "images": []},
            {"url": "https://help.sap.com/brim/p2", "raw_content": "Page 2", "images": []},
        ],
        "response_time": 1.2,
    }
    provider._client.post = MagicMock(return_value=crawl_resp)

    crawl_res = provider.crawl("https://help.sap.com/brim", max_depth=2, limit=10)
    assert len(crawl_res.pages) == 2
    assert crawl_res.discovered_urls == [
        "https://help.sap.com/brim/p1",
        "https://help.sap.com/brim/p2",
    ]

    # Map test
    map_resp = MagicMock()
    map_resp.status_code = 200
    map_resp.json.return_value = {
        "base_url": "https://help.sap.com/brim",
        "results": [
            "https://help.sap.com/brim/a",
            "https://help.sap.com/brim/b",
        ],
        "response_time": 0.3,
    }
    provider._client.post = MagicMock(return_value=map_resp)

    map_res = provider.map_site("https://help.sap.com/brim", max_depth=1)
    assert map_res.urls == [
        "https://help.sap.com/brim/a",
        "https://help.sap.com/brim/b",
    ]


# ---------------------------------------------------------------------------
# Unified Search Service & Fallback Tests
# ---------------------------------------------------------------------------

def test_unified_search_falls_back_to_searxng_on_siftdog_failure():
    service = UnifiedSearchService()

    # Siftdog fails with connection error
    service.siftdog.search = MagicMock(side_effect=SearchProviderUnavailableError("Siftdog down"))

    # SearXNG succeeds
    service.searxng.search = MagicMock(return_value=[
        SearchHit(
            title="SearXNG Rescued Result",
            url="https://help.sap.com/rescued",
            snippet="Rescued by SearXNG",
            raw_content="Content",
            score=1.0,
        )
    ])

    hits = service.search("SAP Subscription Order Management", provider="siftdog")
    assert len(hits) == 1
    assert hits[0].title == "SearXNG Rescued Result"
    assert service.searxng.search.called


def test_unified_search_image_routing_prefers_searxng():
    service = UnifiedSearchService()

    service.searxng.search_images = MagicMock(return_value=[
        ImageHit(
            url="https://help.sap.com/flow.png",
            thumbnail_url="https://help.sap.com/thumb.png",
            source_url="https://help.sap.com/flow",
            source_title="SOM Process Flow",
            resolution="1200x800",
            img_format="PNG",
        )
    ])

    images = service.search_images("Show SOM process flow diagram")
    assert len(images) == 1
    assert images[0].url == "https://help.sap.com/flow.png"
    assert images[0].source_title == "SOM Process Flow"
    assert service.searxng.search_images.called


# ---------------------------------------------------------------------------
# Backward Compatibility Tests with WebSearchService
# ---------------------------------------------------------------------------

def test_web_search_service_delegates_to_unified_search_in_normal_runtime():
    service = WebSearchService()
    service.client = None  # Non-mocked client, activates unified search

    with patch.object(
        service,
        "search_sap_authoritative",
        wraps=service.search_sap_authoritative,
    ), patch(
        "backend.app.services.web_search_service.unified_search_service.search",
        return_value=[
            SearchHit(
                title="SAP Convergent Charging",
                url="https://help.sap.com/cc",
                snippet="Convergent Charging pricing logic",
                raw_content="Detailed pricing logic for subscriptions",
                score=1.5,
            )
        ],
    ):
        results = service.search_sap_authoritative("SAP Convergent Charging")

    assert len(results) == 1
    r = results[0]
    assert r["title"] == "SAP Convergent Charging"
    assert r["url"] == "https://help.sap.com/cc"
    assert r["domain"] == "help.sap.com"
    assert r["authority_class"] == "official_sap_help"
    assert r["authority_tier"] == 1
    assert "chunk_text" in r
    assert r["source_type"] == "web"
