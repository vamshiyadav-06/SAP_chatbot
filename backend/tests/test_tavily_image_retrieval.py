from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from backend.app.config import settings
from backend.app.services.search.base import ImageHit
from backend.app.services.web_search_service import WebSearchService


@pytest.fixture(autouse=True)
def _image_search_enabled(monkeypatch):
    """Image search runs only with the web fallback on; pin it (and the image limit) instead of
    inheriting WEB_FALLBACK_ENABLED / TAVILY_MAX_IMAGES from the environment or .env."""
    monkeypatch.setattr(settings, "WEB_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "TAVILY_MAX_IMAGES", 4)


def _service_with_response(response):
    service = WebSearchService()
    service.client = MagicMock()
    service.client.search.return_value = response
    return service


def test_visual_intent_is_explicit_and_does_not_match_normal_questions():
    assert WebSearchService.wants_visuals("Show the SAP BRIM architecture diagram")
    assert WebSearchService.wants_visuals("Need a billable item process flow")
    assert not WebSearchService.wants_visuals("What is SAP Convergent Invoicing?")


def test_tavily_images_are_normalized_deduplicated_and_sanitized():
    service = _service_with_response({
        "images": [
            {
                "url": "https://cdn.example.com/brim-flow.png",
                "description": "SAP BRIM billable item process flow",
                "source_url": "https://help.sap.com/brim-flow",
                "source_title": "SAP Help flow",
            },
            {"url": "https://cdn.example.com/brim-flow.png", "description": "duplicate"},
            {"url": "javascript:alert(1)", "description": "SAP BRIM process flow"},
        ],
        "results": [{
            "url": "https://community.sap.com/brim",
            "title": "SAP BRIM architecture",
            "images": [{"url": "https://cdn.example.com/brim-architecture.png", "alt": "SAP BRIM architecture"}],
        }],
    })

    images = service.search_sap_images("Show SAP BRIM process flow diagram")

    assert [image["url"] for image in images] == [
        "https://cdn.example.com/brim-flow.png",
        "https://cdn.example.com/brim-architecture.png",
    ]
    assert images[0]["source_title"] == "SAP Help flow"
    assert images[0]["relevance_score"] is None
    assert all(image["url"].startswith("https://") for image in images)
    assert service.client.search.call_args.kwargs["include_images"] is True
    assert service.client.search.call_args.kwargs["include_image_descriptions"] is True


def test_no_images_or_tavily_failure_degrades_to_empty_images():
    service = _service_with_response({"results": []})
    assert service.search_sap_images("Show SAP BRIM architecture diagram") == []

    service = _service_with_response({})
    service.client.search.side_effect = TimeoutError("timed out")
    assert service.search_sap_images("Show SAP BRIM architecture diagram") == []


def test_image_search_is_off_when_the_web_fallback_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "WEB_FALLBACK_ENABLED", False)
    service = _service_with_response({"images": [{"url": "https://cdn.example.com/brim-flow.png"}]})
    assert service.search_sap_images("Show SAP BRIM process flow diagram") == []
    service.client.search.assert_not_called()


def test_normal_image_search_uses_tavily_and_filters_unsafe_image_urls():
    service = WebSearchService()
    hits = [
        ImageHit(
            url="https://cdn.example.com/sap-brim-flow.png",
            source_url="https://help.sap.com/brim-flow",
            source_title="SAP BRIM process flow",
            description="SAP BRIM billing process flow",
        ),
        ImageHit(url="javascript:alert(1)", source_title="SAP BRIM diagram"),
    ]

    with patch(
        "backend.app.services.web_search_service.unified_search_service.search_images",
        return_value=hits,
    ) as tavily_search:
        results = service.search_sap_images("Show SAP BRIM process flow diagram")

    tavily_search.assert_called_once()
    assert [item["url"] for item in results] == ["https://cdn.example.com/sap-brim-flow.png"]
