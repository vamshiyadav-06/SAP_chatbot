from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class ChatCreate(BaseModel):
    title: Optional[str] = Field(default="New SAP Chat", max_length=255)
    # Start the chat inside one of the user's projects.
    project_id: Optional[str] = Field(default=None, max_length=36)

class ChatUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)

class ChatResponse(BaseModel):
    """Chat metadata only. Messages are served by GET /chats/{id}/messages, which hides provider/model,
    grounding, sources and evidence markers from regular users; embedding them here bypassed that."""
    id: str
    user_id: str
    title: str
    project_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ChatListItem(BaseModel):
    id: str
    user_id: str
    title: str
    project_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = ConfigDict(from_attributes=True)
