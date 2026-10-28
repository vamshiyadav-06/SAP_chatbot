"""Tavily fallback evidence quality: exact-identifier queries, page content, authority, conflicts (mocked)."""

from unittest.mock import MagicMock, patch

from backend.app.config import settings
from backend.app.retrieval.multi_source_compare import MultiSourceComparator
from backend.app.services.reranking_service import reranking_service
from backend.app.services.web_search_service import WebSearchService

RAW_HELP_PAGE = """SAP S/4HANA 2023 documentation

Business Partner overview
The business partner is the central object for customer and supplier data.

Blocking Business Partner Data
Customer and supplier master data can be blocked when the business purpose is completed. The field CVP_XBLCK_B is set for blocked data in the company code segment.

Unrelated navigation and footer text that should not be used as evidence for the claim at all."""


def service_with(results):
    service = WebSearchService.__new__(WebSearchService)
    service.api_key = "test"
    service._cache = {}
    service._cache_ttl = 3600
    service.client = MagicMock()
    service.client.search.return_value = {"results": results}
    return service


def test_search_uses_exact_identifier_and_requests_page_content():
    service = service_with([])
    with patch.object(settings, "WEB_FALLBACK_ENABLED", True), \
            patch.object(service, "_fallback_sap_search", return_value=[]):
        service.search_sap_authoritative("What does CVP_XBLCK_B mean for a blocked business partner?")
    kwargs = service.client.search.call_args_list[0].kwargs
    assert '"CVP_XBLCK_B"' in kwargs["query"]
    assert kwargs["include_raw_content"] is True
    assert kwargs["include_domains"] == ["help.sap.com"]


def test_relevant_page_passage_replaces_snippet_as_evidence():
    service = service_with([{
        "url": "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/bp/blocking.html",
        "title": "Blocking Business Partner Data",
        "content": "Customer and supplier master data can be blocked...",
        "raw_content": RAW_HELP_PAGE,
    }])
    with patch.object(settings, "WEB_FALLBACK_ENABLED", True):
        results = service.search_sap_authoritative("CVP_XBLCK_B blocked business partner")
    r = results[0]
    assert r["content_extracted"] is True
    assert "field CVP_XBLCK_B is set for blocked data" in r["chunk_text"]
    assert "footer text" not in r["chunk_text"]
    assert r["snippet"].startswith("Customer and supplier master data")  # snippet preserved for citations
    assert r["authority_class"] == "official_sap_help"
    assert r["release"] == "SAP S/4HANA 2023"
    assert r["url"].startswith("https://help.sap.com/")
    # Extracted evidence survives web reranking (it used to be overwritten with title+snippet).
    ranked, _ = reranking_service.rerank_web("CVP_XBLCK_B blocked business partner", results, top_n=1)
    assert "CVP_XBLCK_B is set" in ranked[0]["chunk_text"]


def test_hostnames_are_reported_and_classified_without_borrowing_help_portal_authority():
    service = service_with([
        {"url": "https://news.sap.com/2024/01/x", "title": "News", "content": "SAP news about partners."},
        {"url": "https://community.sap.com/t5/x", "title": "Forum", "content": "Try SE16N to unblock."},
        {"url": "https://me.sap.com/notes/2502552", "title": "SAP Note 2502552", "content": "Simplification item check."},
    ])
    with patch.object(settings, "WEB_FALLBACK_ENABLED", True), patch.object(settings, "WEB_RAW_CONTENT_ENABLED", False):
        results = {r["domain"]: r for r in service.search_sap_authoritative("business partner block")}
    assert set(results) == {"news.sap.com", "community.sap.com", "me.sap.com"}
    assert results["news.sap.com"]["authority_class"] == "official_sap_other"
    assert results["community.sap.com"]["authority_class"] == "sap_community"
    assert results["me.sap.com"]["authority_class"] == "sap_support_note"
    assert results["me.sap.com"]["authority_tier"] == 1


def test_community_content_is_not_weighted_like_official_documentation():
    comparator = MultiSourceComparator()
    base = {"chunk_text": "Unblocking business partners.", "snippet": "Unblocking business partners.", "score": 0.9}
    official = comparator.normalize_candidate({**base, "url": "https://help.sap.com/x", "domain": "help.sap.com",
                                               "authority_class": "official_sap_help"}, "web", "q")
    community = comparator.normalize_candidate({**base, "url": "https://community.sap.com/x", "domain": "community.sap.com",
                                                "authority_class": "sap_community"}, "web", "q")
    other = comparator.normalize_candidate({**base, "url": "https://news.sap.com/x", "domain": "news.sap.com",
                                            "authority_class": "official_sap_other"}, "web", "q")
    assert official["source_authority"] > other["source_authority"] > community["source_authority"]
    assert official["provenance"] == "official_web" and community["provenance"] == "forum_web"


def test_internal_and_external_conflict_is_detected_in_comparison():
    comparator = MultiSourceComparator()
    kb = [{"chunk_id": "kb-1", "document_name": "Guide.pdf", "score": 0.9, "rerank_score": 0.9,
           "chunk_text": "The assignment of a blocked supplier to a plant can be removed via transaction XK02."}]
    web = [{"url": "https://help.sap.com/simpl", "domain": "help.sap.com", "authority_class": "official_sap_help",
            "title": "Simplification", "score": 0.9, "rerank_score": 0.9,
            "snippet": "Transactions XK01, XK02 and XK03 are not available in SAP S/4HANA.",
            "chunk_text": "Transactions XK01, XK02 and XK03 are not available in SAP S/4HANA."}]
    with patch("backend.app.retrieval.multi_source_compare.repo_store.search_repo_chunks", return_value=[]), \
            patch("backend.app.retrieval.multi_source_compare.web_search_service.search_sap_authoritative", return_value=web), \
            patch("backend.app.retrieval.multi_source_compare.reranking_service.rerank_web", return_value=(web, 0.9)), \
            patch.object(settings, "WEB_FALLBACK_ENABLED", True):
        result = comparator.execute_multi_source_comparison(
            db=MagicMock(), query="remove supplier block", kb_candidates=kb, repo_source_enabled=False,
            multi_source_compare_enabled=True, web_search_available=True, force_web_search=True,
        )
    comparison = result["comparison"]
    assert comparison["conflicts_detected"] is True
    conflict = next(c for c in comparison["evidence_conflicts"] if c["identifier"] == "XK02")
    assert conflict["cross_source"] is True


def test_raw_content_can_be_disabled_without_changing_other_behavior():
    service = service_with([{"url": "https://help.sap.com/x", "title": "T", "content": "Snippet text here.",
                             "raw_content": RAW_HELP_PAGE}])
    with patch.object(settings, "WEB_FALLBACK_ENABLED", True), patch.object(settings, "WEB_RAW_CONTENT_ENABLED", False):
        result = service.search_sap_authoritative("CVP_XBLCK_B")[0]
    assert result["content_extracted"] is False
    assert result["chunk_text"] == "T\nSnippet text here."
    assert service.client.search.call_args.kwargs["include_raw_content"] is False
