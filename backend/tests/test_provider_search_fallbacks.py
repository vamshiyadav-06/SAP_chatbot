"""Offline regressions for approved LLM failover and retrieval-triggered web search."""

from unittest.mock import MagicMock, patch

from backend.app.config import settings
from backend.app.services.llm_service import LLMService
from backend.app.services.rag_service import rag_service
from backend.app.services.search.unified_service import UnifiedSearchService
from backend.tests.offline_rag import RAG_QUESTION, offline_rag


def test_local_preference_uses_allowed_tiers_in_order():
    with patch.object(settings, "LLM_PROVIDER", "local"), \
            patch.object(settings, "LLM_ALLOWED_PROVIDERS", "openrouter,gemini,groq"):
        assert LLMService()._provider_order() == ["groq", "gemini", "openrouter"]


def test_generation_attempts_each_configured_tier_before_returning_unavailable():
    with patch.object(settings, "LLM_PROVIDER", "groq"), \
            patch.object(settings, "LLM_ALLOWED_PROVIDERS", "groq,gemini,openrouter"):
        service = LLMService()
    service.groq_api_key = "test-groq"
    service.gemini_api_key = "test-gemini"
    service.openrouter_api_key = "test-openrouter"
    service.GROQ_MODELS = ["groq-test"]
    service.GEMINI_MODELS = ["gemini-test"]
    service.OPENROUTER_MODELS = ["openrouter-test"]

    with patch.object(settings, "LLM_PROVIDER", "groq"), \
            patch.object(service, "_call_groq", return_value=None) as groq, \
            patch.object(service, "_call_gemini", return_value=None) as gemini, \
            patch.object(service, "_call_openrouter", return_value=None) as openrouter:
        result = service.generate_answer_result("question", [])

    assert result.available is False
    assert result.providers_attempted == ["groq", "gemini", "openrouter"]
    groq.assert_called_once()
    gemini.assert_called_once()
    openrouter.assert_called_once()


def test_low_document_match_triggers_web_even_if_comparator_is_disabled():
    confidence = {"confidence": 0.83, "should_trigger_tavily": False}
    with patch.object(settings, "AUTO_MULTI_SOURCE_FALLBACK", True), \
            patch.object(settings, "WEB_FALLBACK_ENABLED", True), \
            patch.object(settings, "DOCUMENT_MATCH_THRESHOLD", 0.80), \
            patch.object(settings, "REPO_SOURCE_ENABLED", False), \
            patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", False):
        assert rag_service._should_auto_compare(0.42, confidence) is False
        assert rag_service._should_trigger_web_fallback(0.42, confidence) is True


def test_retrieval_miss_searches_web_in_the_shared_rag_pipeline():
    def weak_rerank(query, candidates, top_n=4):
        rows = [dict(item, score=0.35, rerank_score=0.35) for item in candidates[:top_n]]
        return rows, 0.35, True

    with offline_rag():
        with patch.object(settings, "AUTO_MULTI_SOURCE_FALLBACK", True), \
                patch.object(settings, "WEB_FALLBACK_ENABLED", True), \
                patch.object(settings, "REPO_SOURCE_ENABLED", False), \
                patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", False), \
                patch("backend.app.services.rag_service.reranking_service.rerank_kb", side_effect=weak_rerank), \
                patch("backend.app.services.rag_service.web_search_service.search_sap_authoritative", return_value=[]) as web_search:
            result = rag_service.process_query(db=MagicMock(), query=RAG_QUESTION)

    web_search.assert_called()
    assert result["external_search_used"] is True


def test_grounding_rejection_retries_once_with_web_evidence():
    web_passage = {
        "source_type": "web",
        "title": "SAP Help",
        "url": "https://help.sap.com/docs/example",
        "domain": "help.sap.com",
        "snippet": "SAP Help documents the requested configuration.",
        "chunk_text": "SAP Help documents the requested configuration in the supported product release.",
        "score": 0.92,
    }
    finalize_count = 0

    def fake_finalize(query, candidate_answer, passages, source_type, scope, guidance, **kwargs):
        nonlocal finalize_count
        finalize_count += 1
        passes = finalize_count > 1
        verification = {
            "passes_grounding_gate": passes,
            "grounding_score": 0.92 if passes else 0.25,
            "verification_status": "verified" if passes else "rejected",
            "unsupported_claims": [],
            "critical_unsupported_claims": [],
        }
        return candidate_answer, verification, {"attempted": False, "guard_applied": False}, verification["verification_status"]

    with offline_rag():
        with patch.object(settings, "AUTO_MULTI_SOURCE_FALLBACK", True), \
                patch.object(settings, "WEB_FALLBACK_ENABLED", True), \
                patch.object(settings, "REPO_SOURCE_ENABLED", False), \
                patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", False), \
                patch("backend.app.services.rag_service.evidence_selection_service.compute_internal_confidence",
                      return_value={"confidence": 0.92, "should_trigger_tavily": False, "signals": {}}), \
                patch("backend.app.services.rag_service.web_search_service.search_sap_authoritative",
                      return_value=[web_passage]) as web_search, \
                patch.object(rag_service, "_finalize_answer", side_effect=fake_finalize), \
                patch.object(rag_service, "_validation_audit", return_value={"decision": "verified"}):
            result = rag_service.process_query(db=MagicMock(), query=RAG_QUESTION)

    web_search.assert_called_once()
    assert result["source_type"] == "combined"
    assert result["external_search_used"] is True
    assert result["verification_status"] == "verified"


def test_empty_self_hosted_search_results_fall_through_to_tavily():
    service = UnifiedSearchService()
    service.siftdog.search = MagicMock(return_value=[])
    service.searxng.search = MagicMock(return_value=[])
    service.tavily._client = MagicMock()
    expected = [object()]
    service.tavily.search = MagicMock(return_value=expected)

    with patch.object(settings, "SEARCH_PROVIDER", "siftdog"), \
            patch.object(settings, "SEARCH_FALLBACK_TO_SEARXNG", True):
        results = service.search("SAP BRIM configuration", include_domains=["help.sap.com"])

    assert results == expected
    service.siftdog.search.assert_called_once()
    service.searxng.search.assert_called_once()
    service.tavily.search.assert_called_once()


def test_empty_direct_searxng_results_fall_through_to_tavily():
    service = UnifiedSearchService()
    service.searxng.search = MagicMock(return_value=[])
    service.tavily._client = MagicMock()
    expected = [object()]
    service.tavily.search = MagicMock(return_value=expected)

    with patch.object(settings, "SEARCH_PROVIDER", "searxng"):
        results = service.search("SAP BRIM configuration")

    assert results == expected
    service.searxng.search.assert_called_once()
    service.tavily.search.assert_called_once()
