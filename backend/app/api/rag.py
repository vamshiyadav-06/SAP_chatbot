import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.app.database import get_db
from backend.app.schemas.rag import RAGQueryRequest, RAGQueryResponse
from backend.app.services.rag_service import rag_service
from backend.app.models.user import User
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.security.auth import get_current_user


router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/query", response_model=RAGQueryResponse)
def query_rag(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Verify that the chat belongs to the logged-in user
    chat = None

    if request.chat_id:
        chat = db.query(Chat).filter(
            Chat.id == request.chat_id,
            Chat.user_id == current_user.id
        ).first()

        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )

    # 2. Save the user's message
    if chat:
        user_message = Message(
            chat_id=chat.id,
            role="user",
            content=request.query
        )

        db.add(user_message)
        db.commit()
        db.refresh(user_message)

    # 3. Run RAG with chat history if available
    chat_history = []
    if chat and user_message:
        prev_messages = (
            db.query(Message)
            .filter(Message.chat_id == chat.id)
            .filter(Message.id != user_message.id)
            .order_by(Message.created_at.asc())
            .all()
        )
        chat_history = [
            {"role": m.role, "content": m.content, "source_type": m.source_type}
            for m in prev_messages
        ]

    try:
        result = rag_service.process_query(
            db,
            request.query,
            chat_history=chat_history,
            user=current_user
        )

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the SAP query."
        )

    # 4. Save assistant response
    assistant_message_id = None

    if chat:
        assistant_message = Message(
            chat_id=chat.id,
            role="assistant",
            content=result["answer"],
            source_type=result["source_type"],
            grounding_score=result["grounding_score"]
        )

        db.add(assistant_message)

        chat.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(assistant_message)

        assistant_message_id = assistant_message.id

    # 5. Return response
    return RAGQueryResponse(
        answer=result["answer"],
        source_type=result["source_type"],
        grounding_score=result["grounding_score"],
        is_in_rag_pipeline=result.get("is_in_rag_pipeline"),
        kb_score=result.get("kb_score"),
        web_score=result.get("web_score"),
        winning_score=result.get("winning_score"),
        selected_source=result.get("selected_source"),
        verification_status=result.get("verification_status", "verified"),
        internal_evidence_confidence=result.get("internal_evidence_confidence"),
        selected_evidence_quality=result.get("selected_evidence_quality"),
        external_search_used=result.get("external_search_used", False),
        citations=result["citations"],
        web_sources=result["web_sources"],
        follow_up_questions=result.get("follow_up_questions", []),
        selection_summary=result.get("selection_summary"),
        chat_id=chat.id if chat else None,
        message_id=assistant_message_id
    )


@router.post("/query/stream")
def query_rag_stream(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = None
    if request.chat_id:
        chat = db.query(Chat).filter(
            Chat.id == request.chat_id,
            Chat.user_id == current_user.id
        ).first()

    if chat:
        user_message = Message(
            chat_id=chat.id,
            role="user",
            content=request.query
        )
        db.add(user_message)
        db.commit()

    chat_history = []
    if chat and user_message:
        prev_messages = (
            db.query(Message)
            .filter(Message.chat_id == chat.id)
            .filter(Message.id != user_message.id)
            .order_by(Message.created_at.asc())
            .all()
        )
        chat_history = [
            {"role": m.role, "content": m.content, "source_type": m.source_type}
            for m in prev_messages
        ]

    def event_stream():
        accumulated_text = ""
        for event in rag_service.stream_query(db, request.query, chat_history=chat_history, user=current_user):
            if event.get("type") == "token":
                accumulated_text += event.get("content", "")
            elif event.get("type") == "done" and chat:
                full_answer = event.get("answer", accumulated_text)
                assistant_message = Message(
                    chat_id=chat.id,
                    role="assistant",
                    content=full_answer,
                    source_type=event.get("source_type", "knowledge_base"),
                    grounding_score=event.get("grounding_score", 0.0)
                )
                db.add(assistant_message)
                chat.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(assistant_message)
                event["message_id"] = assistant_message.id

            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )