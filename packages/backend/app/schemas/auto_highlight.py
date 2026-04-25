from datetime import datetime
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class AutoHighlightRequest(BaseModel):
    pdf_id: UUID
    categories: list[str] = Field(
        default=["findings"],
        min_length=1,
        description="Categories to highlight",
    )
    pages: Optional[list[int]] = Field(
        default=None,
        description="Page numbers to analyze (1-indexed). None = pages 1-10.",
    )
    tier: Literal["quick", "thorough"] = Field(
        default="quick",
        description="Quick: single-call retrieve-then-extract. Thorough: sequential batches.",
    )


class AutoHighlightResponse(BaseModel):
    cache_id: UUID
    annotation_set_id: Optional[UUID] = None
    from_cache: bool
    highlights_count: int
    pages_analyzed: str = "pending"


class AutoHighlightCacheResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    categories: list[str]  # JSONB
    pages: list[int]  # JSONB
    status: str
    progress_pct: int = 0
    tier: str = "quick"
    created_at: datetime
    annotation_set_id: Optional[UUID] = None


class QuotaResponse(BaseModel):
    free_uses_remaining: int
    has_own_key: bool
    providers: list[str]
