from typing import List, Optional
from pydantic import BaseModel, Field
from backend.app.schemas.citation import CitationResponse, WebSourceResponse, WebImageResponse

class RAGQueryRequest(BaseModel):
    chat_id: Optional[str] = None
    query: str = Field(..., max_length=4000)

class RAGQueryResponse(BaseModel):
    answer: str
    source_type: str  # 'knowledge_base', 'web', 'refusal', 'error', 'combined'
    # None when the answer did not go through retrieval and claim verification.
    grounding_score: Optional[float] = None
    is_in_rag_pipeline: Optional[bool] = None
    kb_score: Optional[float] = None
    web_score: Optional[float] = None
    winning_score: Optional[float] = None
    source_scores: dict[str, float] = Field(default_factory=dict)
    comparison_audit: Optional[dict] = None
    selected_source: Optional[str] = None
    verification_status: Optional[str] = "verified"
    internal_evidence_confidence: Optional[float] = None
    selected_evidence_quality: Optional[float] = None
    external_search_used: Optional[bool] = False
    citations: List[CitationResponse] = []
    web_sources: List[WebSourceResponse] = []
    images: List[WebImageResponse] = []
    follow_up_questions: List[str] = []
    selection_summary: Optional[str] = None
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
