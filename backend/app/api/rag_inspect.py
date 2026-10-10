"""
RAG Inspection API Endpoints
Provides full transparency into the RAG pipeline:
- Document ingestion status (all files in knowledge base, chunk counts, embedding coverage)
- Per-query similarity search with individual chunk scores
- KB confidence signals vs web search score comparison
- Real-time evidence source winner
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.security.auth import get_current_user
from backend.app.models.user import User
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.reranking_service import reranking_service
from backend.app.services.embedding_service import embedding_service
from backend.app.services.evidence_selection_service import evidence_selection_service
from backend.app.services.web_search_service import web_search_service
from backend.app.services.grounding_service import grounding_service
from backend.app.ingestion.ingest import discover_knowledge_base_files

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag-inspect", tags=["RAG Inspection"])


class SimilarityTestRequest(BaseModel):
    query: str
    top_k: int = 10
    include_web_search: bool = False


@router.get("/documents")
def get_document_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Returns the full ingestion status for every document in the knowledge base.
    For each file: whether it has been indexed, how many chunks, embedding coverage.
    """
    discovered_files = discover_knowledge_base_files()
    discovered_names = {f.name for f in discovered_files}

    indexed_docs = db.query(Document).all()
    indexed_map: Dict[str, Dict] = {}
    for doc in indexed_docs:
        chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count()
        embedded_count = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc.id)
            .filter(DocumentChunk.embedding != None)
            .count()
        )
        indexed_map[doc.filename] = {
            "document_id": str(doc.id),
            "title": doc.title,
            "filename": doc.filename,
            "page_count": doc.page_count,
            "chunk_count": chunk_count,
            "embedded_count": embedded_count,
            "embedding_coverage": round(embedded_count / chunk_count, 4) if chunk_count > 0 else 0.0,
            "is_indexed": chunk_count > 0,
            "status": "indexed" if chunk_count > 0 else "empty",
            "file_hash": doc.file_hash,
        }

    documents = []
    for file_path in discovered_files:
        filename = file_path.name
        file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2) if file_path.exists() else 0
        if filename in indexed_map:
            doc_info = dict(indexed_map[filename])
            doc_info["file_size_mb"] = file_size_mb
            doc_info["file_path"] = str(file_path)
            documents.append(doc_info)
        else:
            documents.append({
                "document_id": None,
                "title": filename.replace(".pdf", "").replace("_", " "),
                "filename": filename,
                "file_size_mb": file_size_mb,
                "file_path": str(file_path),
                "page_count": 0,
                "chunk_count": 0,
                "embedded_count": 0,
                "embedding_coverage": 0.0,
                "is_indexed": False,
                "status": "not_indexed",
                "file_hash": None,
            })

    for filename, info in indexed_map.items():
        if filename not in discovered_names:
            info_copy = dict(info)
            info_copy["file_size_mb"] = 0
            info_copy["file_path"] = "FILE_NOT_ON_DISK"
            info_copy["status"] = "orphaned"
            documents.append(info_copy)

    total_chunks = db.query(DocumentChunk).count()
    total_embedded = db.query(DocumentChunk).filter(DocumentChunk.embedding != None).count()

    return {
        "summary": {
            "total_files_discovered": len(discovered_files),
            "total_files_indexed": sum(1 for d in documents if d["is_indexed"]),
            "total_files_not_indexed": sum(1 for d in documents if not d["is_indexed"]),
            "total_chunks": total_chunks,
            "total_embedded_chunks": total_embedded,
            "overall_embedding_coverage": round(total_embedded / total_chunks, 4) if total_chunks > 0 else 0.0,
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dim": settings.EMBEDDING_DIM,
            "internal_evidence_threshold": settings.INTERNAL_EVIDENCE_THRESHOLD,
            "grounding_threshold": settings.ANSWER_GROUNDING_THRESHOLD,
            "web_fallback_enabled": settings.WEB_FALLBACK_ENABLED,
        },
        "documents": documents
    }


@router.post("/similarity-search")
def test_similarity_search(
    request: SimilarityTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Runs full retrieval + reranking for the given query and returns per-chunk scores,
    internal evidence confidence signals, web search results, source comparison, and winner.
    """
    query = request.query.strip()
    if not query:
        return {"error": "Query cannot be empty"}

    kb_candidates = retrieval_service.hybrid_search(db, query, top_k=max(request.top_k * 2, 50))
    top_kb_chunks, kb_rerank_score, has_sufficient = reranking_service.rerank_kb(
        query, kb_candidates, top_n=request.top_k
    )

    internal_confidence_data = evidence_selection_service.compute_internal_confidence(
        query, top_kb_chunks
    )
    internal_conf = internal_confidence_data["confidence"]
    should_trigger_tavily = internal_confidence_data["should_trigger_tavily"]

    web_results = []
    web_score = 0.0
    web_triggered = False
    if (should_trigger_tavily or request.include_web_search) and settings.WEB_FALLBACK_ENABLED:
        web_triggered = True
        try:
            raw_web = web_search_service.search_sap_authoritative(query)
            if raw_web:
                top_web, web_score = reranking_service.rerank_web(query, raw_web, top_n=5)
                web_results = top_web
        except Exception as e:
            logger.warning(f"Web search error: {e}")

    evidence_selection = evidence_selection_service.select_strongest_evidence(
        query=query,
        internal_candidates=top_kb_chunks,
        external_candidates=web_results,
        internal_confidence_data=internal_confidence_data
    )
    selected_source = evidence_selection.get("source_type", "knowledge_base")
    selected_quality = evidence_selection.get("selected_evidence_quality", 0.0)

    chunk_rows = []
    for i, chunk in enumerate(top_kb_chunks[:request.top_k]):
        chunk_rows.append({
            "rank": i + 1,
            "chunk_id": str(chunk.get("chunk_id", "")),
            "document_name": chunk.get("document_name", ""),
            "page_number": chunk.get("page_number", 0),
            "section": chunk.get("section", ""),
            "vector_score": round(float(chunk.get("vector_score", 0.0)), 4),
            "keyword_score": round(float(chunk.get("keyword_score", 0.0)), 4),
            "hybrid_score": round(float(chunk.get("score", 0.0)), 4),
            "rerank_score": round(float(chunk.get("rerank_score", chunk.get("score", 0.0))), 4),
            "snippet": (chunk.get("chunk_text", ""))[:300] + ("..." if len(chunk.get("chunk_text", "")) > 300 else ""),
        })

    web_rows = []
    for i, w in enumerate(web_results[:5]):
        web_rows.append({
            "rank": i + 1,
            "title": w.get("title", ""),
            "url": w.get("url", ""),
            "domain": w.get("domain", ""),
            "score": round(float(w.get("score", w.get("rerank_score", 0.0))), 4),
            "authority_tier": w.get("authority_tier", 2),
            "snippet": (w.get("snippet", ""))[:300],
        })

    kb_wins = selected_source in ("knowledge_base", "combined")

    return {
        "query": query,
        "retrieval_summary": {
            "total_candidates_retrieved": len(kb_candidates),
            "chunks_after_reranking": len(top_kb_chunks),
            "top_kb_rerank_score": round(kb_rerank_score, 4),
            "has_sufficient_kb_evidence": has_sufficient,
        },
        "internal_confidence": {
            "confidence": round(internal_conf, 4),
            "confidence_pct": f"{internal_conf * 100:.1f}%",
            "threshold": settings.INTERNAL_EVIDENCE_THRESHOLD,
            "passes_threshold": internal_conf >= settings.INTERNAL_EVIDENCE_THRESHOLD,
            "would_trigger_web_search": should_trigger_tavily,
            "signals": internal_confidence_data.get("signals", {}),
            "reason": internal_confidence_data.get("reason", ""),
        },
        "web_search": {
            "triggered": web_triggered,
            "results_count": len(web_results),
            "top_web_score": round(web_score, 4),
            "results": web_rows,
        },
        "evidence_selection": {
            "selected_source": selected_source,
            "selected_evidence_quality": round(selected_quality, 4),
            "kb_wins": kb_wins,
            "web_wins": selected_source == "web",
            "summary": evidence_selection.get("selection_summary", ""),
            "internal_eval": evidence_selection.get("internal_eval", {}),
            "external_eval": evidence_selection.get("external_eval", {}),
            "combined_eval": evidence_selection.get("combined_eval", {}),
        },
        "score_comparison": {
            "kb_score": round(internal_conf, 4),
            "kb_score_pct": f"{internal_conf * 100:.1f}%",
            "web_score": round(web_score, 4),
            "web_score_pct": f"{web_score * 100:.1f}%",
            "winning_source": selected_source,
            "winning_score": round(selected_quality, 4),
            "winning_score_pct": f"{selected_quality * 100:.1f}%",
            "score_difference": round(abs(internal_conf - web_score), 4),
        },
        "top_chunks": chunk_rows,
    }
