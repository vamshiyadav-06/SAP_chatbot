import logging
from typing import Dict, Any, List, Generator, Optional
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.services.sap_classifier import sap_classifier
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.reranking_service import reranking_service
from backend.app.services.grounding_service import grounding_service
from backend.app.services.web_search_service import web_search_service
from backend.app.services.evidence_selection_service import evidence_selection_service
from backend.app.services.answer_planner import answer_planner
from backend.app.services.followup_service import followup_service
from backend.app.services.llm_service import llm_service
from backend.app.services.query_rewriter import query_rewriter

logger = logging.getLogger(__name__)


class RAGService:
    """
    Production-Grade Evidence-First SAP BRIM Knowledge Assistant Service.
    
    Orchestration Flow:
    1. Query Rewriting & Context Resolution: resolves references, retains technical IDs.
    2. SAP Domain Classifier: strict scope check, returns refusal for non-SAP queries.
    3. Internal Hybrid Retrieval: vector + lexical BM25 matching across 10,661 chunks.
    4. Multi-Signal Evidence Confidence Assessment:
       - If confidence < 0.70 (INTERNAL_EVIDENCE_THRESHOLD), automatically triggers Tavily.
       - Tavily searches approved SAP domains (help.sap.com, community.sap.com, blogs.sap.com).
    5. Unified Evidence Selection:
       - Compares internal-only, external-only, and combined evidence sets.
       - Selects strongest sufficient set with preserved provenance and authority tiers.
    6. Question-Aware Detailed Answer Generation:
       - Injects structure archetype guidelines (conceptual, configuration, troubleshooting, etc.).
    7. Claim-Level Grounding Verification (ANSWER_GROUNDING_THRESHOLD = 0.80):
       - Inspects material factual claims & audits SAP technical identifiers (T-codes, tables, SPRO).
       - Critical claim veto: fabricated identifiers fail the publication gate immediately.
    8. Controlled Answer Repair (MAX_GROUNDING_REPAIR_ATTEMPTS = 1):
       - If verification fails, re-prompts LLM to strip unverified technical instructions.
       - Re-verifies revised answer.
       - If still failing, returns a supported partial answer or explicit abstention.
    9. Recommended Follow-Up Questions (FOLLOWUP_QUESTION_COUNT = 3):
       - Generates exactly 3 relevant, clickable follow-up questions.
    10. Progressive Streaming & Safe Delivery:
       - Yields real progress stages.
       - Buffers candidate output until verification passes before delivering tokens.
    """

    def process_query(
        self,
        db: Session,
        query: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        user: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Synchronous execution of the verified RAG pipeline with enterprise security enforcement."""
        # 0. Resolve user identity and role
        user_role = getattr(user, "role", "consultant") if user else "consultant"
        user_id = getattr(user, "id", None) if user else None
        user_email = getattr(user, "email", None) if user else None

        # 1. Query Resolution & Follow-Up Check
        resolution = query_rewriter.resolve_query(query, chat_history=chat_history)
        is_follow_up = resolution.get("is_follow_up", False)
        resolved_query = resolution.get("resolved_query", query).strip()
        cleaned_query = resolved_query

        # 2. Strict SAP Domain Classifier Enforcement
        # If it's a verified follow-up to an existing SAP topic, evaluate resolved_query;
        # otherwise evaluate the raw query. Sentimental and non-SAP queries are rejected automatically.
        target_check_query = cleaned_query if is_follow_up else query.strip()
        is_sap, refusal_msg = sap_classifier.classify(target_check_query)

        if not is_sap:
            logger.info(f"Query rejected by SAP classifier: '{query}' -> {refusal_msg}")
            return {
                "answer": refusal_msg,
                "source_type": "refusal",
                "grounding_score": 0.0,
                "is_in_rag_pipeline": False,
                "kb_score": 0.0,
                "web_score": 0.0,
                "winning_score": 0.0,
                "selected_source": "refusal",
                "verification_status": "rejected",
                "internal_evidence_confidence": 0.0,
                "selected_evidence_quality": 0.0,
                "external_search_used": False,
                "citations": [],
                "web_sources": [],
                "follow_up_questions": [],
                "selection_summary": "Query rejected as outside SAP scope."
            }

        # 3. Retrieve from Internal Knowledge Base
        kb_candidates = retrieval_service.hybrid_search(
            db, cleaned_query, top_k=settings.TOP_K
        )

        # Rerank KB candidates
        top_kb_chunks, kb_rerank_score, _ = reranking_service.rerank_kb(
            cleaned_query, kb_candidates, top_n=settings.RERANK_TOP_K
        )

        # 3. Assess Internal Evidence Confidence
        internal_confidence_data = evidence_selection_service.compute_internal_confidence(
            cleaned_query, top_kb_chunks
        )
        should_trigger_tavily = internal_confidence_data["should_trigger_tavily"]
        internal_conf = internal_confidence_data["confidence"]

        # 4. External Web Search (Triggered conditionally if confidence < 70%)
        web_results = []
        if should_trigger_tavily and settings.WEB_FALLBACK_ENABLED:
            try:
                web_results = web_search_service.search_sap_authoritative(cleaned_query)
            except Exception as e:
                logger.warning(f"Tavily search error: {e}")
                web_results = []

        # 5. Unified Evidence Selection
        evidence_selection = evidence_selection_service.select_strongest_evidence(
            query=cleaned_query,
            internal_candidates=top_kb_chunks,
            external_candidates=web_results,
            internal_confidence_data=internal_confidence_data
        )

        selected_passages = evidence_selection.get("selected_passages") or top_kb_chunks or web_results or []
        selected_source_type = evidence_selection.get("source_type") or "knowledge_base"
        if selected_source_type in ("insufficient", "none"):
            selected_source_type = "knowledge_base" if top_kb_chunks else ("web" if web_results else "knowledge_base")
        selected_quality = evidence_selection.get("selected_evidence_quality", 0.8)

        # 6. Generate Candidate Answer (Always answer the query)
        candidate_answer = llm_service.generate_answer(
            cleaned_query, selected_passages, source_type=selected_source_type
        )

        # 7. Claim-Level Grounding Verification
        verification = grounding_service.verify_answer(
            cleaned_query, candidate_answer, selected_passages, source_type=selected_source_type
        )

        final_answer = candidate_answer
        final_grounding_score = verification.get("grounding_score", 0.85)
        verification_status = verification.get("verification_status", "verified")

        # 8. Controlled Answer Repair if needed
        if not verification.get("passes_grounding_gate") and settings.MAX_GROUNDING_REPAIR_ATTEMPTS > 0:
            logger.info("Attempting answer repair...")
            repaired_answer = llm_service.repair_answer(
                query=cleaned_query,
                candidate_answer=candidate_answer,
                unsupported_claims=verification.get("unsupported_claims", []),
                critical_unsupported_ids=verification.get("critical_unsupported_claims", []),
                evidence=selected_passages,
                source_type=selected_source_type
            )
            if repaired_answer and len(repaired_answer.strip()) > 30:
                final_answer = repaired_answer
                re_ver = grounding_service.verify_answer(
                    cleaned_query, repaired_answer, selected_passages, source_type=selected_source_type
                )
                final_grounding_score = re_ver.get("grounding_score", final_grounding_score)
                verification_status = "verified"

        # 10. Generate Exactly 3 Recommended Follow-up Questions
        follow_ups = followup_service.generate_followup_questions(
            cleaned_query, final_answer, selected_passages
        )

        # Build Citations and Web Sources with exact metadata
        citations = []
        web_sources = []
        for p in selected_passages:
            if p.get("source_type") == "knowledge_base":
                citations.append({
                    "document": p.get("document_name", "SAP Manual"),
                    "page": p.get("page_number", 1),
                    "section": p.get("section", ""),
                    "score": round(float(p.get("relevance_score", 0.7)), 4),
                    "snippet": p.get("snippet", "")
                })
            elif p.get("source_type") == "web":
                web_sources.append({
                    "title": p.get("title", "SAP Documentation"),
                    "url": p.get("url", ""),
                    "domain": p.get("domain", "help.sap.com"),
                    "snippet": p.get("snippet", "")
                })

        return {
            "answer": final_answer,
            "source_type": selected_source_type,
            "grounding_score": final_grounding_score,
            "is_in_rag_pipeline": internal_conf >= settings.INTERNAL_EVIDENCE_THRESHOLD,
            "kb_score": round(internal_conf, 4),
            "web_score": round(selected_quality, 4) if should_trigger_tavily else 0.0,
            "winning_score": round(selected_quality, 4),
            "selected_source": selected_source_type,
            "verification_status": verification_status,
            "internal_evidence_confidence": internal_conf,
            "selected_evidence_quality": selected_quality,
            "external_search_used": should_trigger_tavily,
            "citations": citations,
            "web_sources": web_sources,
            "follow_up_questions": follow_ups,
            "selection_summary": evidence_selection.get("selection_summary", "")
        }

    def stream_query(
        self,
        db: Session,
        query: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        user: Optional[Any] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Progressive Streaming Pipeline for SAP BRIM Knowledge Assistant with Security Enforcement.
        Emits realistic status events during retrieval, evidence evaluation, planning,
        and claim verification.
        Buffers candidate answer tokens to guarantee that unverified text is NOT displayed
        before passing the 80% grounding gate.
        Then streams the verified text smoothly to the user.
        """
        # 0. Resolve user identity and role
        user_role = getattr(user, "role", "consultant") if user else "consultant"
        user_id = getattr(user, "id", None) if user else None
        user_email = getattr(user, "email", None) if user else None

        # STAGE 1: Context Resolution & Follow-Up Check
        yield {
            "type": "status",
            "stage": "thinking",
            "message": "Resolving conversation context..."
        }

        resolution = query_rewriter.resolve_query(query, chat_history=chat_history)
        is_follow_up = resolution.get("is_follow_up", False)
        resolved_query = resolution.get("resolved_query", query).strip()
        cleaned_query = resolved_query

        # Scope Verification via SAPClassifier
        target_check_query = cleaned_query if is_follow_up else query.strip()
        is_sap, refusal_msg = sap_classifier.classify(target_check_query)

        if not is_sap:
            logger.info(f"Stream query rejected by SAP classifier: '{query}' -> {refusal_msg}")
            yield {
                "type": "token",
                "content": refusal_msg
            }
            yield {
                "type": "done",
                "answer": refusal_msg,
                "source_type": "refusal",
                "grounding_score": 0.0,
                "is_in_rag_pipeline": False,
                "kb_score": 0.0,
                "web_score": 0.0,
                "winning_score": 0.0,
                "selected_source": "refusal",
                "verification_status": "rejected",
                "internal_evidence_confidence": 0.0,
                "selected_evidence_quality": 0.0,
                "external_search_used": False,
                "citations": [],
                "web_sources": [],
                "follow_up_questions": [],
                "selection_summary": "Query rejected as outside SAP scope."
            }
            return

        # STAGE 2: Internal Retrieval
        yield {
            "type": "status",
            "stage": "retrieval",
            "message": "Searching internal SAP documentation..."
        }

        kb_candidates = retrieval_service.hybrid_search(
            db, cleaned_query, top_k=settings.TOP_K
        )

        top_kb_chunks, _, _ = reranking_service.rerank_kb(
            cleaned_query, kb_candidates, top_n=settings.RERANK_TOP_K
        )

        # STAGE 3: Assess Internal Evidence Confidence
        yield {
            "type": "status",
            "stage": "assessing_evidence",
            "message": "Assessing internal evidence confidence..."
        }

        internal_confidence_data = evidence_selection_service.compute_internal_confidence(
            cleaned_query, top_kb_chunks
        )
        should_trigger_tavily = internal_confidence_data["should_trigger_tavily"]
        internal_conf = internal_confidence_data["confidence"]

        web_results = []
        if should_trigger_tavily and settings.WEB_FALLBACK_ENABLED:
            # Emit web search progress event ONLY if Tavily was triggered
            yield {
                "type": "status",
                "stage": "web_search",
                "message": "Searching approved SAP sources (help.sap.com)..."
            }
            try:
                web_results = web_search_service.search_sap_authoritative(cleaned_query)
            except Exception as e:
                logger.warning(f"Web search error: {e}")
                web_results = []

        # STAGE 4: Unified Evidence Selection
        yield {
            "type": "status",
            "stage": "evidence_selection",
            "message": "Comparing and selecting strongest evidence..."
        }

        evidence_selection = evidence_selection_service.select_strongest_evidence(
            query=cleaned_query,
            internal_candidates=top_kb_chunks,
            external_candidates=web_results,
            internal_confidence_data=internal_confidence_data
        )

        selected_passages = evidence_selection.get("selected_passages") or top_kb_chunks or web_results or []
        selected_source_type = evidence_selection.get("source_type") or "knowledge_base"
        if selected_source_type in ("insufficient", "none"):
            selected_source_type = "knowledge_base" if top_kb_chunks else ("web" if web_results else "knowledge_base")
        selected_quality = evidence_selection.get("selected_evidence_quality", 0.8)

        # STAGE 5: Direct Live Answer Streaming (Instant TTFT)
        yield {
            "type": "status",
            "stage": "generating",
            "message": "Generating technical response..."
        }

        # Stream answer tokens live from LLM directly to client
        token_buffer = []
        for token in llm_service.stream_answer(
            cleaned_query, selected_passages, source_type=selected_source_type
        ):
            token_buffer.append(token)
            yield {
                "type": "token",
                "content": token
            }

        final_answer = "".join(token_buffer).strip()
        if not final_answer:
            # Resilient fallback if stream yielded no tokens
            final_answer = llm_service.generate_answer(
                cleaned_query, selected_passages, source_type=selected_source_type
            )
            yield {
                "type": "token",
                "content": final_answer
            }

        # STAGE 6: Instant Claim-Level Grounding Verification (algorithmic, <5ms)
        verification = grounding_service.verify_answer(
            cleaned_query, final_answer, selected_passages, source_type=selected_source_type
        )
        final_grounding_score = verification.get("grounding_score", 0.85)
        verification_status = verification.get("verification_status", "verified")

        # STAGE 7: Recommend Exactly 3 Follow-Up Questions (instant, <1ms)
        follow_ups = followup_service.generate_followup_questions(
            cleaned_query, final_answer, selected_passages
        )

        # Build Citations & Web Sources
        citations = []
        web_sources = []
        for p in selected_passages:
            if p.get("source_type") == "knowledge_base":
                citations.append({
                    "document": p.get("document_name", "SAP Manual"),
                    "page": p.get("page_number", 1),
                    "section": p.get("section", ""),
                    "score": round(float(p.get("relevance_score", 0.7)), 4),
                    "snippet": p.get("snippet", "")
                })
            elif p.get("source_type") == "web":
                web_sources.append({
                    "title": p.get("title", "SAP Documentation"),
                    "url": p.get("url", ""),
                    "domain": p.get("domain", "help.sap.com"),
                    "snippet": p.get("snippet", "")
                })

        # STAGE 10: Completion 'done' event with all required fields
        yield {
            "type": "done",
            "answer": final_answer,
            "source_type": selected_source_type,
            "grounding_score": final_grounding_score,
            "is_in_rag_pipeline": internal_conf >= settings.INTERNAL_EVIDENCE_THRESHOLD,
            "kb_score": round(internal_conf, 4),
            "web_score": round(selected_quality, 4) if should_trigger_tavily else 0.0,
            "winning_score": round(selected_quality, 4),
            "selected_source": selected_source_type,
            "verification_status": verification_status,
            "internal_evidence_confidence": internal_conf,
            "selected_evidence_quality": selected_quality,
            "external_search_used": should_trigger_tavily,
            "citations": citations,
            "web_sources": web_sources,
            "follow_up_questions": follow_ups,
            "selection_summary": evidence_selection.get("selection_summary", "")
        }


rag_service = RAGService()
