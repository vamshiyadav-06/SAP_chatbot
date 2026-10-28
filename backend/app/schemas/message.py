from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from backend.app.schemas.citation import CitationResponse, WebSourceResponse, WebImageResponse


class DocumentAttachment(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    file_type: Optional[str] = Field(default="pdf", max_length=32)
    size_bytes: Optional[int] = 0
    page_count: Optional[int] = None
    text: str = Field(..., min_length=1, max_length=150000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.replace("\\", "/").split("/")[-1].strip()
        if not value:
            raise ValueError("Attachment filename cannot be empty.")
        return value


class DocumentExtractResponse(BaseModel):
    filename: str
    file_type: str
    size_bytes: int
    page_count: int
    char_count: int
    preview: str
    text: str
    # Images only: the question/error found in the image, and how it was read
    # ("vision", "vision+ocr" or "ocr").
    detected_question: Optional[str] = None
    analysis_method: Optional[str] = None


class UploadedAttachmentInfo(BaseModel):
    name: str
    file_type: str
    page_count: Optional[int] = None
    size_bytes: Optional[int] = None


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=200000)
    attachments: Optional[List[DocumentAttachment]] = Field(default=None, max_length=5)


class MessageFeedback(BaseModel):
    # None clears the rating.
    value: Optional[Literal["up", "down"]] = None


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
    verification_status: Optional[str] = "verified"
    internal_evidence_confidence: Optional[float] = None
    selected_evidence_quality: Optional[float] = None
    external_search_used: Optional[bool] = False
    created_at: datetime
    citations: List[CitationResponse] = []
    web_sources: List[WebSourceResponse] = []
    images: List[WebImageResponse] = []
    follow_up_questions: List[str] = []
    attachments: Optional[List[UploadedAttachmentInfo]] = None
    feedback: Optional[Literal["up", "down"]] = None

    model_config = ConfigDict(from_attributes=True)
