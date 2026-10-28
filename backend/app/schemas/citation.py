from pydantic import BaseModel, ConfigDict
from typing import Optional

class CitationResponse(BaseModel):
    id: Optional[str] = None
    chunk_id: Optional[str] = None
    source_type: Optional[str] = None
    document: str
    page: int
    section: Optional[str] = None
    score: float
    snippet: str
    ref: Optional[str] = None  # inline evidence marker (e.g. "E2") this citation backs

    model_config = ConfigDict(from_attributes=True)

class WebSourceResponse(BaseModel):
    id: Optional[str] = None
    title: str
    url: str
    domain: str
    snippet: str
    ref: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class WebImageResponse(BaseModel):
    url: str
    description: Optional[str] = None
    alt_text: Optional[str] = None
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    relevance_score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)
