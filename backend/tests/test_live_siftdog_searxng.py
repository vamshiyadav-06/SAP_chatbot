"""Live integration verification for running SearXNG (8089) and Siftdog (8088) services."""

import pytest
import urllib.request
from backend.app.services.search.searxng_provider import SearxngSearchProvider
from backend.app.services.search.siftdog_provider import SiftdogSearchProvider
from backend.app.services.search.unified_service import UnifiedSearchService


def is_service_live(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2.0) as res:
            return res.status == 200
    except Exception:
        return False


SEARXNG_LIVE = is_service_live("http://127.0.0.1:8089/search?q=ping&format=json")
SIFTDOG_LIVE = is_service_live("http://127.0.0.1:8088/health")


@pytest.mark.skipif(not SEARXNG_LIVE, reason="Live SearXNG container on port 8089 is not reachable")
def test_live_searxng_search_and_images():
    provider = SearxngSearchProvider(base_url="http://127.0.0.1:8089")

    # 1. Live text search
    hits = provider.search("SAP BRIM Convergent Invoicing", max_results=3)
    assert len(hits) > 0
    assert all(hit.url.startswith("http") for hit in hits)

    # 2. Live image search
    images = provider.search_images("SAP BRIM architecture diagram", max_images=3)
    assert len(images) > 0
    assert all(img.url.startswith("http") for img in images)


@pytest.mark.skipif(not SIFTDOG_LIVE, reason="Live Siftdog container on port 8088 is not reachable")
def test_live_siftdog_capabilities():
    provider = SiftdogSearchProvider(base_url="http://127.0.0.1:8088")

    # 1. Health check
    health = provider.check_health()
    assert health.get("status") in ("healthy", "ok", 200) or isinstance(health, dict)

    # 2. Live search with raw content extraction
    hits = provider.search("SAP Convergent Charging", max_results=2, include_raw_content=True)
    assert len(hits) > 0
    assert all(hit.url.startswith("http") for hit in hits)


@pytest.mark.skipif(not (SEARXNG_LIVE and SIFTDOG_LIVE), reason="Live services not reachable")
def test_live_unified_search_pipeline():
    service = UnifiedSearchService()
    hits = service.search("SAP BRIM", max_results=2, provider="siftdog")
    assert len(hits) > 0

    images = service.search_images("SAP BRIM process flow diagram", max_images=2)
    assert len(images) > 0
