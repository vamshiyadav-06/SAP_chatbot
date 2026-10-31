from unittest.mock import MagicMock, patch

from backend.app.config import settings
from backend.app.retrieval.multi_source_compare import MultiSourceComparator
from backend.app.services.llm_service import LLMService
from backend.app.services.rag_service import RAGService


def test_document_match_below_80_percent_triggers_multisource_search():
    confidence = {"confidence": 0.9, "should_trigger_tavily": False}
    # Auto-fallback needs an explicitly enabled extra source (AUDIT_REPORT F-49).
    with patch.object(settings, "AUTO_MULTI_SOURCE_FALLBACK", True), patch.object(
        settings, "DOCUMENT_MATCH_THRESHOLD", 0.80
    ), patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", True):
        assert RAGService._should_auto_compare(0.799, confidence) is True
        assert RAGService._should_auto_compare(0.80, confidence) is False


def test_low_confidence_also_triggers_search_even_when_top_match_is_high():
    confidence = {"confidence": 0.65, "should_trigger_tavily": True}
    with patch.object(settings, "AUTO_MULTI_SOURCE_FALLBACK", True), patch.object(
        settings, "MULTI_SOURCE_COMPARE_ENABLED", True
    ):
        assert RAGService._should_auto_compare(0.90, confidence) is True


def test_comparator_searches_github_and_web_then_selects_highest_weighted_match():
    comparator = MultiSourceComparator()
    db = MagicMock()
    kb = [{
        "chunk_id": "kb-1",
        "document_name": "SAP BRIM.pdf",
        "chunk_text": "A weaker document passage about billable items.",
        "score": 0.70,
        "rerank_score": 0.70,
    }]
    web = [{
        "source_id": "sap-help-1",
        "title": "SAP Help: Billable Item Processing",
        "url": "https://help.sap.com/docs/example",
        "domain": "help.sap.com",
        "snippet": "SAP Convergent Invoicing processes billable items through documented steps.",
        "score": 0.92,
        "rerank_score": 0.92,
        "chunk_text": "SAP Convergent Invoicing processes billable items through documented steps.",
    }]
    with patch.object(settings, "WEB_FALLBACK_ENABLED", True),             patch("backend.app.retrieval.multi_source_compare.repo_store.search_repo_chunks", return_value=[]) as repo_search, patch(
        "backend.app.retrieval.multi_source_compare.web_search_service.search_sap_authoritative",
        return_value=web,
    ) as web_search, patch(
        "backend.app.retrieval.multi_source_compare.reranking_service.rerank_web",
        return_value=(web, 0.92),
    ):
        result = comparator.execute_multi_source_comparison(
            db=db,
            query="SAP Convergent Invoicing billable items",
            kb_candidates=kb,
            repo_source_enabled=True,
            multi_source_compare_enabled=True,
            web_search_available=True,
            force_web_search=True,
        )

    repo_search.assert_called_once()
    web_search.assert_called_once()
    assert result["comparison"]["sources_compared"] == ["knowledge_base", "github_repo", "web"]
    assert result["comparison"]["winning_source_type"] == "web"
    assert result["winning_candidate"]["final_score"] > 0.70


def test_answer_temperature_is_configurable_and_capped_for_grounded_generation():
    with patch.object(settings, "ANSWER_TEMPERATURE", 0.8):
        service = LLMService()
    assert service.generation_temperature == 0.3
