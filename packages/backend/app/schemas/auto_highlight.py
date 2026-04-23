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
    page_start: int = Field(default=1, ge=1, description="First page to analyze (1-indexed)")
    page_end: int = Field(default=10, ge=1, description="Last page to analyze (inclusive)")

    @property
    def page_count(self) -> int:
        return self.page_end - self.page_start + 1


class AutoHighlightResponse(BaseModel):
    annotation_set_id: UUID
    from_cache: bool
    highlights_count: int
    pages_analyzed: str = "all"


class AutoHighlightCacheResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    categories: Any  # JSONB
    page_start: int
    page_end: int
    created_at: datetime
    annotation_set_id: Optional[UUID] = None


class QuotaResponse(BaseModel):
    free_uses_remaining: int
    has_own_key: bool
    providers: list[str]
