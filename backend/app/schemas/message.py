from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from backend.app.schemas.citation import CitationResponse, WebSourceResponse

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)

class MessageResponse(BaseModel):
    id: str
    chat_id: str
    role: str
    content: str
    source_type: Optional[str] = None
    grounding_score: Optional[float] = None
    is_in_rag_pipeline: Optional[bool] = None
    kb_score: Optional[float] = None
    web_score: Optional[float] = None
    winning_score: Optional[float] = None
    created_at: datetime
    citations: List[CitationResponse] = []
    web_sources: List[WebSourceResponse] = []

    model_config = ConfigDict(from_attributes=True)
