from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class AutoHighlightRequest(BaseModel):
    pdf_id: UUID
    categories: list[str] = Field(
        default=["findings"],
        min_length=1,
        description="Categories to highlight",
    )


class AutoHighlightResponse(BaseModel):
    annotation_set_id: UUID
    from_cache: bool
    highlights_count: int
    pages_analyzed: str = "all"
    provider_fallback: bool = False


class AutoHighlightCacheResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    categories: Any  # JSONB
    created_at: datetime
    annotation_set_id: Optional[UUID] = None


class QuotaResponse(BaseModel):
    free_uses_remaining: int
    has_own_key: bool
    providers: list[str]
