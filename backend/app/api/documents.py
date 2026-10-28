import json
import logging
import asyncio
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Header, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.models.user import User
from backend.app.security.auth import oauth2_scheme, get_optional_current_user, admin_key_matches
from backend.app.services.document_processing_service import document_processing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Document Management"])


def authenticate_document_operator(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    Strictly enforces administrator privileges.
    Allows operations with valid X-Admin-Key header or authenticated admin JWT token.
    """
    if admin_key_matches(x_admin_key):
        return True
    user = get_optional_current_user(token=token, db=db)
    if user and user.is_admin:
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unauthorized: Document management is strictly restricted to authorized Super Administrators.",
    )


class ProcessRequest(BaseModel):
    force: bool = False
    document_ids: Optional[List[str]] = None


@router.get("", summary="List knowledge base documents with statuses, filters, and chunk metrics")
def get_documents(
    status: Optional[str] = Query(None, description="Filter by status: all, pending, processing, completed, failed"),
    search: Optional[str] = Query(None, description="Search by filename or title"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    auth: Any = Depends(authenticate_document_operator),
):
    return document_processing_service.get_documents(
        db=db,
        status_filter=status,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/processing-status", summary="Get real-time live processing statistics and current document progress")
def get_processing_status(
    auth: Any = Depends(authenticate_document_operator),
):
    return document_processing_service.get_progress_status()


@router.get("/processing-stream", summary="Server-Sent Events (SSE) live stream for processing progress")
async def stream_processing_progress(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    header_token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    effective_token = header_token
    is_authorized = False
    if admin_key_matches(x_admin_key):
        is_authorized = True
    elif effective_token:
        user = get_optional_current_user(token=effective_token, db=db)
        if user and user.is_admin:
            is_authorized = True

    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Stream access is restricted to authorized administrators.",
        )

    async def event_generator():
        q = document_processing_service.subscribe()
        try:
            # Send immediate state on connect
            init_state = document_processing_service.get_progress_status()
            yield f"data: {json.dumps(init_state)}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=12.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive ping
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            document_processing_service.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



@router.post("/upload", summary="Upload multiple documents through file picker", status_code=status.HTTP_201_CREATED)
async def upload_documents(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    auth: Any = Depends(authenticate_document_operator),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    registered = []
    errors = []

    for file in files:
        try:
            file_bytes = await file.read()
            if not file_bytes:
                errors.append({"filename": file.filename, "error": "File is empty (0 bytes)."})
                continue

            doc_info = document_processing_service.register_uploaded_file(
                filename=file.filename,
                file_bytes=file_bytes,
                db=db,
            )
            registered.append(doc_info)
        except Exception as e:
            logger.error(f"Failed to upload '{file.filename}': {e}")
            errors.append({"filename": file.filename, "error": str(e)})

    return {
        "status": "success" if registered else "error",
        "registered_count": len(registered),
        "documents": registered,
        "errors": errors,
    }


@router.post("/process-all", summary="Process all pending and failed documents in one operation")
def process_all_documents(
    req: Optional[ProcessRequest] = Body(default=None),
    auth: Any = Depends(authenticate_document_operator),
):
    force = req.force if req else False
    doc_ids = req.document_ids if req else None
    result = document_processing_service.start_processing(document_ids=doc_ids, force=force)
    return result


@router.post("/{document_id}/process", summary="Process or retry an individual document")
def process_individual_document(
    document_id: str,
    req: Optional[ProcessRequest] = Body(default=None),
    db: Session = Depends(get_db),
    auth: Any = Depends(authenticate_document_operator),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    force = req.force if req else True
    result = document_processing_service.start_processing(document_ids=[document_id], force=force)
    return result


@router.get("/{document_id}", summary="Get detailed document metadata and sample chunk inspect")
def get_document_details(
    document_id: str,
    db: Session = Depends(get_db),
    auth: Any = Depends(authenticate_document_operator),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc.id)
        .order_by(DocumentChunk.chunk_index)
        .limit(20)
        .all()
    )
    total_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count()

    chunks_data = []
    for c in chunks:
        chunks_data.append({
            "id": str(c.id),
            "chunk_index": c.chunk_index,
            "page_number": c.page_number,
            "section": c.section,
            "text_preview": c.chunk_text[:200] + ("..." if len(c.chunk_text) > 200 else ""),
            "has_embedding": c.embedding is not None,
        })

    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "title": doc.title,
        "file_type": doc.file_type,
        "file_size_bytes": doc.file_size_bytes,
        "file_hash": doc.file_hash,
        "page_count": doc.page_count,
        "chunk_count": total_chunks,
        "status": doc.status,
        "stage": doc.stage,
        "error_message": doc.error_message,
        "vector_indexed": doc.vector_indexed,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "sample_chunks": chunks_data,
    }


@router.delete("/{document_id}", summary="Delete document from knowledge base, purge vectors and disk file")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    auth: Any = Depends(authenticate_document_operator),
):
    try:
        result = document_processing_service.delete_document(document_id=document_id, db=db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete document '{document_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {e}")
