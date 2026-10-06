import json
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.citation import Citation
from backend.app.models.web_source import WebSource
from backend.app.schemas.message import MessageCreate, MessageResponse
from backend.app.security.auth import get_current_user
from backend.app.services.rag_service import rag_service
from backend.app.services.llm_service import llm_service
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.reranking_service import reranking_service
from backend.app.services.grounding_service import grounding_service
from backend.app.services.web_search_service import web_search_service
from backend.app.services.sap_classifier import sap_classifier
from backend.app.config import settings

router = APIRouter(prefix="/chats/{chat_id}/messages", tags=["Messages"])

def verify_chat_ownership(chat_id: str, user_id: str, db: Session) -> Chat:
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user_id).first()
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat

@router.get("", response_model=List[MessageResponse])
def get_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_chat_ownership(chat_id, current_user.id, db)
    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    result = []
    for msg in messages:
        c_list = [
            {
                "id": c.id,
                "document": c.document_name,
                "page": c.page_number,
                "section": c.section,
                "score": c.similarity_score,
                "snippet": c.citation_text
            }
            for c in msg.citations
        ]
        w_list = [
            {
                "id": w.id,
                "title": w.title,
                "url": w.url,
                "domain": w.domain,
                "snippet": w.snippet
            }
            for w in msg.web_sources
        ]
        result.append(
            MessageResponse(
                id=msg.id,
                chat_id=msg.chat_id,
                role=msg.role,
                content=msg.content,
                source_type=msg.source_type,
                grounding_score=msg.grounding_score,
                created_at=msg.created_at,
                citations=c_list,
                web_sources=w_list
            )
        )
    return result

@router.post("")
def send_message(
    chat_id: str,
    msg_in: MessageCreate,
    stream: bool = Query(False, description="Enable Server-Sent Events (SSE) streaming"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = verify_chat_ownership(chat_id, current_user.id, db)

    # 1. Save user message
    user_msg = Message(
        chat_id=chat_id,
        role="user",
        content=msg_in.content.strip()
    )
    db.add(user_msg)
    
    # Auto-generate chat title from first question if default
    if chat.title == "New SAP Chat" or not chat.title:
        words = msg_in.content.strip().split()
        chat.title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")

    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user_msg)

    # 2. Check SSE streaming flow
    if stream:
        return handle_streaming_response(chat_id, msg_in.content.strip(), db)

    # 3. Synchronous RAG flow
    rag_result = rag_service.process_query(db, msg_in.content.strip())

    # 4. Save assistant message
    assistant_msg = Message(
        chat_id=chat_id,
        role="assistant",
        content=rag_result["answer"],
        source_type=rag_result["source_type"],
        grounding_score=rag_result["grounding_score"]
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    # 5. Persist citations or web sources
    if rag_result["citations"]:
        for c in rag_result["citations"]:
            cit = Citation(
                message_id=assistant_msg.id,
                source_type="knowledge_base",
                document_id="doc-" + c["document"],
                document_name=c["document"],
                chunk_id="chunk-ref",
                page_number=c["page"],
                section=c["section"],
                similarity_score=c["score"],
                citation_text=c["snippet"]
            )
            db.add(cit)
        db.commit()

    if rag_result["web_sources"]:
        for w in rag_result["web_sources"]:
            ws = WebSource(
                message_id=assistant_msg.id,
                url=w["url"],
                title=w["title"],
                domain=w["domain"],
                snippet=w["snippet"]
            )
            db.add(ws)
        db.commit()

    db.refresh(assistant_msg)

    return MessageResponse(
        id=assistant_msg.id,
        chat_id=assistant_msg.chat_id,
        role=assistant_msg.role,
        content=assistant_msg.content,
        source_type=assistant_msg.source_type,
        grounding_score=assistant_msg.grounding_score,
        is_in_rag_pipeline=rag_result.get("is_in_rag_pipeline"),
        kb_score=rag_result.get("kb_score"),
        web_score=rag_result.get("web_score"),
        winning_score=rag_result.get("winning_score"),
        created_at=assistant_msg.created_at,
        citations=[
            {
                "id": c.id,
                "document": c.document_name,
                "page": c.page_number,
                "section": c.section,
                "score": c.similarity_score,
                "snippet": c.citation_text
            }
            for c in assistant_msg.citations
        ],
        web_sources=[
            {
                "id": w.id,
                "title": w.title,
                "url": w.url,
                "domain": w.domain,
                "snippet": w.snippet
            }
            for w in assistant_msg.web_sources
        ]
    )

def handle_streaming_response(chat_id: str, query: str, db: Session):
    """Generates Server-Sent Events (SSE) stream using the complete verified RAG pipeline."""
    def event_stream():
        # Execute unified RAG pipeline with objective score comparison
        result = rag_service.process_query(db, query)
        answer = result["answer"]
        source_type = result["source_type"]
        grounding = result["grounding_score"]
        citations = result["citations"]
        web_sources = result["web_sources"]
        is_in_rag_pipeline = result.get("is_in_rag_pipeline", False)
        kb_score = result.get("kb_score", 0.0)
        web_score = result.get("web_score", 0.0)
        winning_score = result.get("winning_score", 0.0)

        # Save to DB
        assistant_msg = Message(
            chat_id=chat_id,
            role="assistant",
            content=answer,
            source_type=source_type,
            grounding_score=grounding
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)

        if citations:
            for c in citations:
                db.add(Citation(
                    message_id=assistant_msg.id,
                    source_type="knowledge_base",
                    document_id="doc-" + c["document"],
                    document_name=c["document"],
                    chunk_id="chunk-ref",
                    page_number=c["page"],
                    section=c["section"],
                    similarity_score=c["score"],
                    citation_text=c["snippet"]
                ))
            db.commit()

        if web_sources:
            for w in web_sources:
                db.add(WebSource(
                    message_id=assistant_msg.id,
                    url=w["url"],
                    title=w["title"],
                    domain=w["domain"],
                    snippet=w["snippet"]
                ))
            db.commit()

        # Stream event 1: metadata (citations, source_type, grounding_score, scores, message_id)
        meta_payload = {
            "message_id": assistant_msg.id,
            "source_type": source_type,
            "grounding_score": grounding,
            "is_in_rag_pipeline": is_in_rag_pipeline,
            "kb_score": kb_score,
            "web_score": web_score,
            "winning_score": winning_score,
            "citations": citations,
            "web_sources": web_sources
        }
        yield f"event: metadata\ndata: {json.dumps(meta_payload)}\n\n"

        # Stream event 2: tokens
        tokens = answer.split(" ")
        for i, t in enumerate(tokens):
            chunk = t + (" " if i < len(tokens) - 1 else "")
            yield f"event: token\ndata: {json.dumps({'token': chunk})}\n\n"

        # Stream event 3: done (includes complete full_answer for verification)
        yield f"event: done\ndata: {json.dumps({'status': 'complete', 'full_answer': answer})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
