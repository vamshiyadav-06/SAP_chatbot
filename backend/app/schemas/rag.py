from typing import List, Optional
from pydantic import BaseModel
from backend.app.schemas.citation import CitationResponse, WebSourceResponse

class RAGQueryRequest(BaseModel):
    chat_id: Optional[str] = None
    query: str

class RAGQueryResponse(BaseModel):
    answer: str
    source_type: str  # 'knowledge_base', 'web', 'refusal', 'error', 'combined'
    grounding_score: float
    is_in_rag_pipeline: Optional[bool] = None
    kb_score: Optional[float] = None
    web_score: Optional[float] = None
    winning_score: Optional[float] = None
    selected_source: Optional[str] = None
    verification_status: Optional[str] = "verified"
    internal_evidence_confidence: Optional[float] = None
    selected_evidence_quality: Optional[float] = None
    external_search_used: Optional[bool] = False
    citations: List[CitationResponse] = []
    web_sources: List[WebSourceResponse] = []
    follow_up_questions: List[str] = []
    selection_summary: Optional[str] = None
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
