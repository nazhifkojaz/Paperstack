"""Pydantic schemas for chat and semantic search endpoints."""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    pdf_id: Optional[UUID] = None
    collection_id: Optional[UUID] = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pdf_id: Optional[UUID]
    collection_id: Optional[UUID]
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ContextChunkResponse(BaseModel):
    chunk_id: str
    page_number: int
    snippet: str
    pdf_id: Optional[str] = None
    pdf_title: Optional[str] = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    context_chunks: Optional[list[ContextChunkResponse]] = None
    created_at: datetime


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    collection_id: Optional[UUID] = None
    limit: int = Field(default=10, ge=1, le=50)


class SemanticSearchResult(BaseModel):
    pdf_id: UUID
    pdf_title: str
    page_number: int
    snippet: str
    score: float


class ExplainRequest(BaseModel):
    pdf_id: UUID
    annotation_id: UUID
    selected_text: str = Field(min_length=1, max_length=2000)
    page_number: int = Field(ge=1)


class ExplainResponse(BaseModel):
    explanation: str
    note_content: str
    explain_uses_remaining: int
    provider_fallback: bool = False
