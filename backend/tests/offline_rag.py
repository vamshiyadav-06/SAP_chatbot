"""
Offline harness for the RAG pipeline: retrieval, reranking, web search and every LLM call are
stubbed, so process_query / stream_query run end to end without a database or network.
"""

from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from backend.app.config import settings
from backend.app.services.rag_service import rag_service

# Routed through retrieval: "configure" and "step by step" are complex-technical markers.
RAG_QUESTION = "How do I configure the posting area for Convergent Invoicing to FI-CA step by step?"

KB_ROWS: List[Dict[str, Any]] = [
    {
        "chunk_id": "chunk-ci-1",
        "document_id": "doc-1",
        "document_name": "SAP CI1.pdf",
        "source_type": "knowledge_base",
        "page_number": 12,
        "section": "Posting Areas",
        "chunk_text": (
            "Convergent Invoicing transfers invoicing documents to FI-CA. The posting area defines "
            "the account determination used when invoicing documents are posted in FI-CA."
        ),
        "snippet": "Convergent Invoicing transfers invoicing documents to FI-CA.",
        "vector_score": 0.82,
        "bm25_score": 4.1,
        "score": 0.86,
    },
    {
        "chunk_id": "chunk-ci-2",
        "document_id": "doc-1",
        "document_name": "SAP CI1.pdf",
        "source_type": "knowledge_base",
        "page_number": 13,
        "section": "Posting Areas",
        "chunk_text": (
            "Configure the posting area in Customizing for Contract Accounts Receivable and Payable "
            "before running invoicing for the first time."
        ),
        "snippet": "Configure the posting area in Customizing.",
        "vector_score": 0.8,
        "bm25_score": 3.7,
        "score": 0.84,
    },
]

DEFAULT_ANSWER = (
    "Convergent Invoicing transfers invoicing documents to FI-CA [E1]. "
    "The posting area defines the account determination used when invoicing documents are posted [E1]. "
    "Configure the posting area in Customizing before running invoicing for the first time [E2]."
)


@contextmanager
def offline_rag(answer: str = DEFAULT_ANSWER, rows: Optional[List[Dict[str, Any]]] = None, repair: Optional[str] = None):
    """Patch every external dependency of the RAG pipeline; yields a dict that records calls."""
    rows = rows if rows is not None else KB_ROWS
    calls: Dict[str, Any] = {"generate": 0, "stream": 0, "repair": 0, "retrieve": 0}

    def fake_retrieve(db, q, top_k=None, **kwargs):
        calls["retrieve"] += 1
        return [dict(r) for r in rows]

    def fake_rerank(query, candidates, top_n=4):
        return [dict(c) for c in candidates][:max(top_n or 4, 1)], 0.86, True

    def fake_generate(query, evidence, source_type="knowledge_base", **kwargs):
        calls["generate"] += 1
        return answer

    def fake_stream(query, evidence, source_type="knowledge_base", **kwargs):
        calls["stream"] += 1
        for i in range(0, len(answer), 13):
            yield answer[i:i + 13]

    def fake_repair(**kwargs):
        calls["repair"] += 1
        return repair if repair is not None else kwargs["candidate_answer"]

    with patch.object(settings, "AUTO_MULTI_SOURCE_FALLBACK", False), \
            patch.object(settings, "WEB_FALLBACK_ENABLED", False), \
            patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", False), \
            patch.object(settings, "REPO_SOURCE_ENABLED", False), \
            patch.object(settings, "ANSWER_STYLE_LLM_CLASSIFIER_ENABLED", False), \
            patch.object(rag_service.retrieval, "retrieve", side_effect=fake_retrieve), \
            patch.object(rag_service.retrieval, "hybrid_search", side_effect=fake_retrieve), \
            patch("backend.app.services.rag_service.reranking_service.rerank_kb", side_effect=fake_rerank), \
            patch("backend.app.services.rag_service.web_search_service.search_sap_authoritative", return_value=[]), \
            patch("backend.app.services.rag_service.web_search_service.search_sap_images", return_value=[]), \
            patch("backend.app.services.rag_service.llm_service.generate_answer", side_effect=fake_generate), \
            patch("backend.app.services.rag_service.llm_service.stream_answer", side_effect=fake_stream), \
            patch("backend.app.services.rag_service.llm_service.repair_answer", side_effect=fake_repair):
        yield calls
