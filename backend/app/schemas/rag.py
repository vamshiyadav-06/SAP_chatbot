from typing import List, Optional
from pydantic import BaseModel
from backend.app.schemas.citation import CitationResponse, WebSourceResponse

class RAGQueryRequest(BaseModel):
    chat_id: Optional[str] = None
    query: str

class RAGQueryResponse(BaseModel):
    answer: str
    source_type: str  # 'knowledge_base', 'web', 'refusal', 'error'
    grounding_score: float
    is_in_rag_pipeline: Optional[bool] = None
    kb_score: Optional[float] = None
    web_score: Optional[float] = None
    winning_score: Optional[float] = None
    selected_source: Optional[str] = None
    citations: List[CitationResponse] = []
    web_sources: List[WebSourceResponse] = []
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
