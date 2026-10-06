import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.services.sap_classifier import sap_classifier
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.reranking_service import reranking_service
from backend.app.services.grounding_service import grounding_service
from backend.app.services.web_search_service import web_search_service
from backend.app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class RAGService:
    def process_query(self, db: Session, query: str) -> Dict[str, Any]:
        """
        Executes the full, verified RAG pipeline:
        1. Strict SAP domain restriction validation
        2. Accelerated hybrid retrieval from internal knowledge base
        3. Authoritative SAP web search retrieval
        4. Objective multi-factor reranking & score comparison (KB Score vs Web Score)
        5. Clear notification if query is NOT in internal RAG pipeline
        6. Selection of highest-scoring evidence passed to Groq LLM
        7. Evidence-grounded answer synthesis & grounding score evaluation
        """
        cleaned_query = query.strip()

        # STEP 1: Domain Restriction Validation
        is_sap, reason = sap_classifier.classify(cleaned_query)
        if not is_sap:
            return {
                "answer": "I can only help with SAP and SAP-related topics.",
                "source_type": "refusal",
                "grounding_score": 0.0,
                "is_in_rag_pipeline": False,
                "kb_score": 0.0,
                "web_score": 0.0,
                "winning_score": 0.0,
                "selected_source": "refusal",
                "citations": [],
                "web_sources": []
            }

        # STEP 2: Retrieve from Internal Knowledge Base
        kb_candidates = retrieval_service.hybrid_search(db, cleaned_query, top_k=settings.TOP_K)

        # STEP 3: Retrieve from Authoritative SAP Web Sources if enabled
        web_results = []
        if settings.WEB_FALLBACK_ENABLED:
            try:
                web_results = web_search_service.search_sap_authoritative(cleaned_query)
            except Exception as e:
                logger.warning(f"Web search error: {e}")
                web_results = []

        # STEP 4: Objective Multi-factor Reranking & Score Comparison
        comparison = reranking_service.compare_and_select(
            cleaned_query,
            kb_candidates,
            web_results,
            threshold=settings.SIMILARITY_THRESHOLD
        )

        winner = comparison["winner"]
        is_in_rag_pipeline = comparison["is_in_rag_pipeline"]
        kb_score = comparison["kb_score"]
        web_score = comparison["web_score"]
        winning_score = comparison["winning_score"]
        top_kb_chunks = comparison["top_kb_chunks"]
        top_web_results = comparison["top_web_results"]

        logger.info(
            f"RAG Comparison for '{cleaned_query[:40]}': Winner={winner}, "
            f"KB Score={kb_score:.4f}, Web Score={web_score:.4f}, In-KB={is_in_rag_pipeline}"
        )

        # STEP 5: High Score Execution with Groq LLM

        # Case A: Internal Knowledge Base has the higher score
        if winner == "knowledge_base" and top_kb_chunks:
            answer = llm_service.generate_answer(cleaned_query, top_kb_chunks, source_type="knowledge_base")
            grounding = grounding_service.evaluate_grounding(cleaned_query, answer, top_kb_chunks, source_type="knowledge_base")

            citations = [
                {
                    "document": c["document_name"],
                    "page": c["page_number"],
                    "section": c["section"],
                    "score": c["rerank_score"],
                    "snippet": c["chunk_text"][:280] + ("..." if len(c["chunk_text"]) > 280 else "")
                }
                for c in top_kb_chunks
            ]

            return {
                "answer": answer,
                "source_type": "knowledge_base",
                "grounding_score": grounding,
                "is_in_rag_pipeline": True,
                "kb_score": kb_score,
                "web_score": web_score,
                "winning_score": winning_score,
                "selected_source": "knowledge_base",
                "citations": citations,
                "web_sources": []
            }

        # Case B: Web Search has the higher score (or query is NOT in RAG pipeline)
        if winner == "web" and top_web_results:
            # Inform user if information was not found in internal knowledge base
            if not is_in_rag_pipeline:
                prefix = (
                    f"*(Notice: This topic was not found in the internal SAP Knowledge Base "
                    f"[KB Relevance: {kb_score:.2f}]. Retrieved from authoritative SAP web documentation "
                    f"[Web Score: {web_score:.2f}].)*\n\n"
                )
            else:
                prefix = (
                    f"*(Notice: Authoritative SAP web documentation scored higher "
                    f"[{web_score:.2f} vs KB {kb_score:.2f}].)*\n\n"
                )

            llm_answer = llm_service.generate_answer(cleaned_query, top_web_results, source_type="web")
            full_answer = prefix + llm_answer

            grounding = grounding_service.evaluate_grounding(
                cleaned_query, llm_answer, top_web_results, source_type="web"
            )

            web_sources = [
                {
                    "title": w["title"],
                    "url": w["url"],
                    "domain": w["domain"],
                    "snippet": w["snippet"]
                }
                for w in top_web_results[:3]
            ]

            return {
                "answer": full_answer,
                "source_type": "web",
                "grounding_score": grounding,
                "is_in_rag_pipeline": is_in_rag_pipeline,
                "kb_score": kb_score,
                "web_score": web_score,
                "winning_score": winning_score,
                "selected_source": "web",
                "citations": [],
                "web_sources": web_sources
            }

        # Case C: Insufficient information everywhere
        notice = (
            f"I couldn't find sufficient information about this in either the internal "
            f"SAP knowledge base (Relevance Score: {kb_score:.2f}) or authoritative SAP web documentation "
            f"(Relevance Score: {web_score:.2f})."
        )
        return {
            "answer": notice,
            "source_type": "knowledge_base",
            "grounding_score": 0.0,
            "is_in_rag_pipeline": False,
            "kb_score": kb_score,
            "web_score": web_score,
            "winning_score": winning_score,
            "selected_source": "none",
            "citations": [],
            "web_sources": []
        }


rag_service = RAGService()
